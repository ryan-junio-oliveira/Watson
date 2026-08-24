"""Camada de cálculo determinística (§Watson Analista).

Extrai fatos numéricos das evidências, detecta a intenção da pergunta
(percentual, soma, média, diferença, maior/menor) e executa a aritmética em
Python — sem depender do LLM. O resultado é injetado no prompt como um
"dado verificado", e o modelo apenas narra a conclusão.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

MONTHS: List[str] = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]
MONTH_ABBR: List[str] = [
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
]

# Números no formato pt-BR: 1.234,56 | 1,5 | 1234
_NUMBER_RE = re.compile(
    r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?"
)

# Chaves genéricas que não representam dados numéricos de negócio.
_NOISY_KEYS = {
    "id", "cod", "codigo", "código", "page", "pagina", "página",
    "num", "numero", "número", "versao", "versão", "index", "indice",
    "índice", "hash", "chunk", "peso",
}


@dataclass
class NumericFact:
    label: str
    value: float
    raw: str
    is_month: bool = False
    month_index: int = -1

    @property
    def display_value(self) -> str:
        return format_number(self.value)


@dataclass
class ComputedFact:
    kind: str
    expression: str
    result: float
    facts: List[NumericFact] = field(default_factory=list)
    unit: str = ""

    @property
    def human(self) -> str:
        if self.kind == "percent_change":
            return f"{format_number(abs(self.result))}%"
        return f"{format_number(self.result)} {self.unit}".strip()

    def prompt_block(self) -> str:
        lines = [
            "============================",
            "Fonte: cálculo verificado (determinístico)",
            "Título: Cálculo verificado sobre os dados",
            "",
            f"Dado verificado: {self.expression} = {self.human}",
        ]
        if self.facts:
            detail = "; ".join(f"{f.label}: {f.display_value}" for f in self.facts)
            lines.append(f"Fatos usados: {detail}")
        return "\n".join(lines)


def format_number(value: float) -> str:
    """Formata número no padrão pt-BR (vírgula decimal, sem notação científica)."""
    rounded = round(value, 2)
    if rounded == int(rounded):
        return f"{int(rounded):,}".replace(",", ".")
    s = f"{rounded:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    s = s.rstrip("0").rstrip(",")
    return s or "0"


def parse_number(text: str) -> Optional[float]:
    """Converte número pt-BR (ex.: '1.234,56' -> 1234.56) ou retorna None."""
    t = text.strip()
    # Formato pt-BR com separador de milhar (ex.: '1.234' ou '1.234,56')
    if re.match(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$", t):
        return float(t.replace(".", "").replace(",", "."))
    # Decimal com vírgula (ex.: '15,5')
    if re.match(r"^\d+(?:,\d+)?$", t):
        return float(t.replace(",", "."))
    try:
        return float(t)
    except ValueError:
        return None


class NumberExtractor:
    def extract(self, texts: List[str]) -> List[NumericFact]:
        facts: List[NumericFact] = []
        for text in texts:
            facts.extend(self._extract_from_text(text))
        return self._dedupe(facts)

    def _extract_from_text(self, text: str) -> List[NumericFact]:
        facts: List[NumericFact] = []
        lower = text.lower()
        for line in text.splitlines():
            cleaned = line.strip().strip("|").strip()
            if not cleaned:
                continue
            fact = self._month_fact(cleaned, lower)
            if fact is None:
                fact = self._key_value_fact(cleaned)
            if fact is not None:
                facts.append(fact)
        return facts

    def _month_fact(self, line: str, lower_line: str) -> Optional[NumericFact]:
        idx = self._find_month_index(lower_line)
        if idx < 0:
            return None
        numbers = _NUMBER_RE.findall(line)
        if not numbers:
            return None
        value = parse_number(numbers[0])
        if value is None:
            return None
        label = MONTHS[idx].capitalize()
        return NumericFact(label=label, value=value, raw=line,
                           is_month=True, month_index=idx)

    def _key_value_fact(self, line: str) -> Optional[NumericFact]:
        m = re.match(r"^([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9\s\-\_]*?)\s*[:=\-]\s*(\d[\d.,\s]*)$", line)
        if not m:
            return None
        key = m.group(1).strip().lower()
        if not key or key in _NOISY_KEYS:
            return None
        value = parse_number(m.group(2))
        if value is None:
            return None
        label = m.group(1).strip()
        return NumericFact(label=label, value=value, raw=line)

    @staticmethod
    def _find_month_index(text: str) -> int:
        for i, m in enumerate(MONTHS):
            if m in text:
                return i
        for i, a in enumerate(MONTH_ABBR):
            if re.search(rf"\b{a}\b", text):
                return i
        return -1

    def _dedupe(self, facts: List[NumericFact]) -> List[NumericFact]:
        seen: set = set()
        out: List[NumericFact] = []
        for f in facts:
            key = (f.label.lower(), f.value)
            if key not in seen:
                seen.add(key)
                out.append(f)
        return out


class IntentDetector:
    # Prioridade: percentual > diferença > soma > média > maior > menor
    _RULES = [
        ("percent_change", (
            r"quantos\s*%|% a mais|% a menos|por\s*cento|percentual|"
            r"porcentagem|variação|variacao|percentualmente|cresceu|"
            r"aumentou|diminuiu|caiu\s*\d|proporção|proporcao"
        )),
        ("difference", (
            r"diferença|diferenca|quanto a mais|quanto a menos|"
            r"a mais que|a menos que|quanto ele (?:produziu|imprimiu) a mais"
        )),
        ("sum", (
            r"\btotal\b|totaliza|totalizam|somam|\bsoma\b|quantos ao todo|"
            r"ao todo|quantas ao todo|contagem"
        )),
        ("average", (r"média|media|em média|em media|na média|na media")),
        ("max", (
            r"\bmaior\b|mais alto|recorde|pico|o maximo|o máximo|"
            r"teve\s+mais|tem\s+mais|com\s+mais|imprimiu\s+mais|"
            r"qual\s+(?:mês|mes|periodo|período|ano)\s+.*mais"
        )),
        ("min", (
            r"\bmenor\b|mais baixo|minimo|mínimo|"
            r"teve\s+menos|tem\s+menos|com\s+menos|imprimiu\s+menos"
        )),
    ]

    def detect(self, question: str) -> Optional[str]:
        q = question.lower()
        for kind, patterns in self._RULES:
            if re.search(patterns, q):
                return kind
        return None


class Calculator:
    def __init__(
        self,
        extractor: Optional[NumberExtractor] = None,
        detector: Optional[IntentDetector] = None,
    ):
        self.extractor = extractor or NumberExtractor()
        self.detector = detector or IntentDetector()

    def compute_for_question(
        self, question: str, texts: List[str]
    ) -> Optional[ComputedFact]:
        intent = self.detector.detect(question)
        if intent is None:
            return None
        facts = self.extractor.extract(texts)
        if len(facts) < 2:
            return None
        return self._compute(intent, facts)

    def _compute(self, intent: str, facts: List[NumericFact]) -> Optional[ComputedFact]:
        ordered = sorted(facts, key=lambda f: f.month_index if f.is_month else 0)
        if intent == "percent_change":
            return self._percent_change(ordered)
        if intent == "difference":
            return self._difference(ordered)
        if intent == "sum":
            total = sum(f.value for f in facts)
            return ComputedFact(
                kind="sum",
                expression=f"Soma dos valores ({', '.join(f.display_value for f in facts)})",
                result=total,
                facts=facts,
            )
        if intent == "average":
            total = sum(f.value for f in facts)
            avg = total / len(facts)
            return ComputedFact(
                kind="average",
                expression=(
                    f"Média dos valores "
                    f"({', '.join(f.display_value for f in facts)}) ÷ {len(facts)}"
                ),
                result=avg,
                facts=facts,
            )
        if intent in ("max", "min"):
            pick = max(facts, key=lambda f: f.value) if intent == "max" else min(
                facts, key=lambda f: f.value
            )
            detail = ", ".join(f"{f.label}: {f.display_value}" for f in facts)
            return ComputedFact(
                kind=intent,
                expression=(
                    f"Maior valor ({detail})"
                    if intent == "max"
                    else f"Menor valor ({detail})"
                ),
                result=pick.value,
                facts=[pick],
            )
        return None

    def _ordered_pair(self, facts: List[NumericFact]) -> Optional[tuple]:
        """Retorna (earlier, later) quando há dois fatos comparáveis."""
        months = [f for f in facts if f.is_month]
        if len(months) >= 2:
            months.sort(key=lambda f: f.month_index)
            return months[0], months[1]
        if len(facts) == 2:
            return facts[0], facts[1]
        return None

    def _percent_change(self, facts: List[NumericFact]) -> Optional[ComputedFact]:
        pair = self._ordered_pair(facts)
        if pair is None:
            return None
        earlier, later = pair
        if earlier.value == 0:
            return None
        change = (later.value - earlier.value) / earlier.value * 100
        expr = (
            f"Variação de {earlier.label} ({earlier.display_value}) para "
            f"{later.label} ({later.display_value}): "
            f"({later.display_value} - {earlier.display_value}) / {earlier.display_value} x 100"
        )
        return ComputedFact(
            kind="percent_change",
            expression=expr,
            result=change,
            facts=[earlier, later],
            unit="%",
        )

    def _difference(self, facts: List[NumericFact]) -> Optional[ComputedFact]:
        pair = self._ordered_pair(facts)
        if pair is None:
            return None
        earlier, later = pair
        diff = later.value - earlier.value
        expr = (
            f"Diferença de {earlier.label} ({earlier.display_value}) para "
            f"{later.label} ({later.display_value}): "
            f"{later.display_value} - {earlier.display_value}"
        )
        return ComputedFact(
            kind="difference",
            expression=expr,
            result=diff,
            facts=[earlier, later],
        )
