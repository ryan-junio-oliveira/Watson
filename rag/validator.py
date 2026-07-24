import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from llm.ollama_client import OllamaClient
from rag.evidence import Evidence, EvidenceAggregator


VALIDATOR_SYSTEM_PROMPT = (
    'Você é um verificador de consistência. Sua função é verificar se as '
    "afirmações na resposta são apoiadas APENAS pelas evidências fornecidas.\n"
    "NÃO use seu próprio conhecimento — use SOMENTE as evidências.\n\n"
    "Cada evidência contém a URL da fonte e o conteúdo extraído da página.\n\n"
    "Retorne APENAS um JSON válido, sem formatação adicional, sem markdown:\n"
    "{{\n"
    '  "claims": [\n'
    "    {{\n"
    '      "claim": "afirmação extraída",\n'
    '      "status": "supported" | "unsupported" | "contradicts",\n'
    '      "evidence_snippet": "trecho que apoia/refuta ou null",\n'
    '      "confidence": 0.0 a 1.0\n'
    "    }}\n"
    "  ],\n"
    '  "overall_verdict": "consistent" | "inconsistent" | "partial",\n'
    '  "overall_confidence": 0.0 a 1.0,\n'
    '  "issues": ["problemas encontrados"]\n'
    "}}\n\n"
    "Evidências (use APENAS estas para verificar):\n"
    "{evidence}\n\n"
    "Resposta a verificar:\n"
    "{answer}"
)


@dataclass
class ValidationResult:
    claims: List[Dict[str, Any]] = field(default_factory=list)
    overall_verdict: str = "unknown"
    overall_confidence: float = 0.0
    issues: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.overall_verdict == "consistent"

    @property
    def supported_ratio(self) -> float:
        if not self.claims:
            return 0.0
        supported = sum(1 for c in self.claims if c.get("status") == "supported")
        return supported / len(self.claims)


class ConfidenceScorer:
    MIN_CONFIDENCE = 0.5

    @staticmethod
    def calculate(
        validation: ValidationResult,
        evidence: List[Evidence],
    ) -> float:
        base = 0.0

        if validation.overall_verdict == "consistent":
            base = 0.7 + (validation.overall_confidence * 0.3)
        elif validation.overall_verdict == "partial":
            base = 0.3 + (validation.overall_confidence * 0.4)
        elif validation.overall_verdict == "inconsistent":
            base = 0.1

        support_ratio = validation.supported_ratio
        base *= 0.5 + 0.5 * support_ratio

        num_sources = len(evidence)
        if num_sources >= 3:
            base *= 1.1
        elif num_sources >= 1:
            base *= 1.0
        else:
            base *= 0.5

        source_types = set(e.source_type for e in evidence)
        if "rag" in source_types and "web" in source_types:
            base *= 1.1

        return min(max(base, 0.0), 1.0)

    @staticmethod
    def should_reject(confidence: float) -> bool:
        return confidence < ConfidenceScorer.MIN_CONFIDENCE


class FactValidator:
    def __init__(
        self,
        ollama_client: OllamaClient,
        logger: Optional[logging.Logger] = None,
        validation_timeout: int = 15,
    ):
        self.ollama_client = ollama_client
        self.logger = logger
        self.validation_timeout = validation_timeout

    def validate(
        self,
        answer: str,
        evidence: List[Evidence],
    ) -> ValidationResult:
        if not evidence:
            return ValidationResult(
                claims=[],
                overall_verdict="inconsistent",
                overall_confidence=0.0,
                issues=["Nenhuma evidência fornecida para verificar a resposta"],
            )

        evidence_text = EvidenceAggregator().format_for_prompt(evidence)

        prompt = VALIDATOR_SYSTEM_PROMPT.format(
            evidence=evidence_text,
            answer=answer,
        )

        try:
            import ollama
            temp_client = ollama.Client(
                host=self.ollama_client.base_url,
                timeout=self.validation_timeout,
            )
            response = temp_client.generate(
                model=self.ollama_client.model,
                prompt=prompt,
                options={
                    "temperature": 0.0,
                    "num_predict": 512,
                },
            )
            raw = response.get("response", "")
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                raw = raw.rsplit("```", 1)[0]
            data = json.loads(raw)
            result = ValidationResult(
                claims=data.get("claims", []),
                overall_verdict=data.get("overall_verdict", "unknown"),
                overall_confidence=float(data.get("overall_confidence", 0.0)),
                issues=data.get("issues", []),
            )
            if self.logger:
                self.logger.info(
                    f"Validation: verdict={result.overall_verdict}, "
                    f"confidence={result.overall_confidence:.2f}, "
                    f"claims={len(result.claims)}, issues={len(result.issues)}"
                )
            return result
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Validation failed: {e}")
            return ValidationResult(
                overall_verdict="unknown",
                overall_confidence=0.0,
                issues=[f"Erro na validação: {e}"],
            )
