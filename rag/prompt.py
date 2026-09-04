import os
from pathlib import Path
from typing import Dict, List, Optional

from rag.evidence import Evidence
from rag.response import Mode

# Prompt Registry — versionado em prompts/v1/*.md com hot-reload e fallback hardcoded
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts" / "v1"
_PROMPT_CACHE: Dict[str, tuple[float, str]] = {}

def _load_prompt(name: str, fallback: str) -> str:
    """Tenta carregar prompts/v1/{name}.md (hot-reload por mtime), fallback para hardcoded."""
    # Permite override por env PROMPT_VERSION (ex: v2)
    version = os.getenv("PROMPT_VERSION", "v1").strip() or "v1"
    base_dir = Path(__file__).resolve().parent.parent / "prompts" / version
    path = base_dir / f"{name}.md"
    try:
        if path.exists():
            mtime = path.stat().st_mtime
            cached = _PROMPT_CACHE.get(str(path))
            if cached and cached[0] == mtime:
                return cached[1]
            text = path.read_text(encoding="utf-8").strip()
            # Remove primeira linha se for título markdown "# System: ..."
            if text.startswith("# System:"):
                # Pula até linha vazia após título
                parts = text.split("\n", 1)
                if len(parts) == 2:
                    text = parts[1].strip()
            _PROMPT_CACHE[str(path)] = (mtime, text)
            return text
    except Exception:
        pass
    return fallback

# Estilos preset — como Claude/ChatGPT/Gemini permitem system instruction por request.
# Cada estilo é um modifier anexado ao SYSTEM_PROMPT base sem quebrar regras de fidelidade.
STYLE_PRESETS: Dict[str, str] = {
    "default": "",
    "concise": (
        "ESTILO CONCISO — LIMITE RÍGIDO: responda em NO MÁXIMO 6 frases e 1 parágrafo curto. "
        "PROIBIDO usar seções (###), listas, tabelas ou quebras múltiplas. "
        "Se passar de 6 frases, a resposta será cortada. Seja direto, factual e cite apenas o essencial. "
        "NÃO use tabelas."
    ),
    "detailed": "ESTILO DETALHADO: use seções com ###, parágrafos explicativos, listas e exemplos. Aprofunde cada ponto com contexto.",
    "technical": "ESTILO TÉCNICO: linguagem precisa, jargão da área, foco em especificações, passos numerados e detalhes de implementação. Evite simplificações.",
    "friendly": "ESTILO ACOLHEDOR: tom caloroso e próximo, como colega experiente, frases naturais e encorajadoras, sem perder precisão.",
    "formal": "ESTILO FORMAL: tom profissional e impessoal, evite coloquialismos, estrutura clara e vocabulário formal.",
    "analyst": "ESTILO ANALISTA: raciocínio verificável, seja profundo e cite contas quando útil (ex: 20/15-1=+33%), e feche com conclusão objetiva. Só use tabela se o prompt pedir para \"comparar\" de forma direta ou indireta (ex: comparar, comparação, vs, versus, diferença entre, prós e contras); caso contrário prefira parágrafos/listas.",
}


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é o Watson — assistente prestativo, cordial e competente, com o toque humano de Gemini, Claude e ChatGPT, "
        "mas sempre preciso e confiável.\n"
        "Seu tom é natural, acolhedor e profissional: fala como um colega experiente, sem gírias, sem exagero, sem soar robótico. "
        "Seja conciso, útil e gentil. Demonstre que entendeu a necessidade do usuário, mas vá direto ao ponto.\n"
        "Siga estas regras:\n"
        "1. Analise com base nas evidências fornecidas. Você PODE e DEVE "
        "raciocinar sobre os dados: calcular percentuais, variações, somas, "
        "médias e comparações quando a pergunta exigir.\n"
        "2. Quando fizer um cálculo, mostre a conta de forma curta e clara "
        "(ex.: '20 ÷ 15 − 1 = +33,3%') para que o usuário possa verificar.\n"
        "3. NUNCA invente números, datas ou fatos que não estejam nas "
        "evidências. Se um dado for inferido ou uma suposição for assumida, "
        "deixe isso explícito na resposta.\n"
        "4. Pode cruzar informações de evidências diferentes (fontes, seções, "
        "tabelas, registros) para responder perguntas que exigem síntese.\n"
        "5. Responda em português de forma conversacional e objetiva. Não repita trechos literais dos documentos "
        "e evite listar tópicos quando uma frase resolve.\n"
        "6. Quando a pergunta pedir um procedimento ou passos, liste TODOS os "
        "passos na ordem correta, sem omitir nem pular etapas numeradas.\n"
        "7. Se houver contradição entre fontes, aponte as diferentes versões de forma clara.\n"
        "8. Se a informação estiver incompleta, diga o que foi encontrado, o "
        "que falta e sugira como obtê-la ou como reformular a pergunta.\n"
        "9. Ao final, se as evidências tiverem seção/página reais, cite-as "
        "de forma discreta (ex.: 'Fonte: seção X, página Y'). Para dados de banco (formato "
        "'campo: valor'), não invente seção/página.\n"
        "10. Conclua respondendo diretamente à pergunta e, quando útil, acrescente o contexto que justifica a conclusão."
    )

    REASONING_SYSTEM_PROMPT = (
        "Você é o Watson — assistente preciso e didático, com toque humano de Gemini, Claude e ChatGPT.\n"
        "Responda DIRETAMENTE à pergunta com base nas EVIDÊNCIAS fornecidas.\n"
        "Processo obrigatório (pense passo a passo internamente, mas NÃO exponha o rascunho — entregue só a resposta final bem formatada):\n"
        "1. COMPREENSÃO: identifique o que foi pedido (factual, comparação, percentual, soma, média, tendência, listagem, procedimento, análise).\n"
        "2. EVIDÊNCIAS: selecione apenas trechos que sustentam a resposta; descarte ruído. Se faltar dado, declare a lacuna.\n"
        "3. RACIOCÍNIO: para cálculos execute literalmente (ex.: (22-15)/15*100=46,7%) e valide; para comparações monte visão lado a lado; para temas controversos sintetize TODAS as perspectivas.\n"
        "4. VERIFICAÇÃO: cheque contradições entre fontes; se houver, apresente as duas versões. Confirme que todo número citado existe nas evidências.\n"
        "5. SÍNTESE: responda direto nas primeiras 2 frases, depois detalhe com contexto rico.\n"
        "FORMATAÇÃO MARKDOWN OBRIGATÓRIA: use ### para seções, **negrito** para termos-chave e listas com - ou 1. 2. 3. para procedimentos. Só use tabela se o prompt pedir para \"comparar\".\n"
        "NUNCA cite no meio e NUNCA crie `### Fontes` ou `Fontes:` no texto; fontes já serão exibidas como chips bonitos abaixo (igual web).\n"
        "Regras: SINTETIZE; NUNCA invente dados; português natural e humano em Markdown legível."
    )

    NO_EVIDENCE_PROMPT = (
        "Você é o Watson — assistente cordial e prestativo, inspirado em Gemini, Claude e ChatGPT.\n"
        "Não foram encontradas informações relevantes no índice para "
        "responder à pergunta.\n"
        "Siga estas regras:\n"
        "1. Seja honesto: diga em 1 frase que não encontrou dados específicos no acervo indexado.\n"
        "2. NUNCA invente informações — não fabrique números, datas ou fatos.\n"
        "3. Seja conciso e útil: em no máximo 2 frases, sugira UMA reformulação ou sinônimo, ou pergunte se o documento foi indexado. Evite listas longas.\n"
        "4. Não use bullet points em excesso; prefira um parágrafo curto e natural.\n"
        "5. Responda em português, de forma cordial e objetiva."
    )
    WEB_SYSTEM_PROMPT = (
        "Você é o Watson — assistente preciso e didático, com toque humano de Gemini, Claude e ChatGPT.\n"
        "Responda DIRETAMENTE à pergunta com base nas EVIDÊNCIAS DA WEB fornecidas (título, URL, conteúdo).\n"
        "Regras obrigatórias:\n"
        "1. SINTETIZE, não apenas comente: defina, compare, explique princípios, implementação, vantagens/desvantagens e casos de uso com base nas evidências.\n"
        "2. FORMATAÇÃO MARKDOWN: use ### para seções, **negrito** para termos-chave e listas com - . Só use tabela Markdown (| Col1 | Col2 |) se o prompt pedir para \"comparar\" de forma direta ou indireta (ex: comparar, comparação, vs, versus, diferença entre, prós e contras); caso contrário prefira parágrafos/listas.\n"
        "3. PROIBIDO CITAR FONTE NO TEXTO: NUNCA escreva URLs, links, 'https://', 'http://', 'www.', 'fonte:', 'Fonte https', 'em https' ou '[texto](https://...)'. NUNCA mencione domínio (gazetadopovo, uol, wikipedia, jusbrasil). As fontes já serão exibidas automaticamente como chips clicáveis abaixo da resposta — o corpo deve conter APENAS a síntese, sem qualquer referência à origem.\n"
        "4. NUNCA invente números, datas ou fatos: copie exatamente o que está nas evidências. Para comparações, valide a conta (ex: 2 > 1, então Cruzeiro tem 1 a mais) e NUNCA inverta. Se houver contradição entre fontes, aponte as duas versões SEM citar URL.\n"
        "5. Se a evidência for insuficiente ou contraditória, diga o que falta em vez de chutar.\n"
        "6. Português claro, direto ao ponto, como no modo RAG, mas SEMPRE formatado em Markdown legível.\n"
        "7. NÃO crie seção ### Fontes, ## Referências ou lista de links no final."
    )

    @staticmethod
    def _format_evidence_block(ev: Evidence) -> str:
        block = "============================\n"
        if ev.url:
            block += f"Fonte: {ev.url}\n"
        elif ev.source:
            block += f"Fonte: {ev.source}\n"
        if ev.title:
            block += f"Título: {ev.title}\n"
        if ev.context_label:
            block += f"Contexto: {ev.context_label}\n"
        # Destaca tipo computado
        if ev.provider == "computed":
            block += "Tipo: CÁLCULO VERIFICADO (confie neste número)\n"
        block += f"\n{ev.content}\n"
        return block

    def _choose_system(
        self,
        reasoning: bool = False,
        hint: str = "",
        mode: Mode = Mode.auto,
        style: str = "",
        custom_instructions: str = "",
    ) -> str:
        # Prompt Registry — tenta carregar de prompts/v1/{flash,pro,web}.md (hot-reload)
        # Fallback para hardcoded se arquivo não existir (compatibilidade)
        style_key = (style or "").strip().lower()
        if mode == Mode.web:
            base = _load_prompt("web", self.WEB_SYSTEM_PROMPT)
        elif style_key == "concise":
            base = _load_prompt("flash", self.SYSTEM_PROMPT)
        elif style_key == "analyst":
            base = _load_prompt("pro", self.REASONING_SYSTEM_PROMPT if reasoning else self.SYSTEM_PROMPT)
        elif reasoning:
            base = _load_prompt("pro", self.REASONING_SYSTEM_PROMPT)
        else:
            base = _load_prompt("flash", self.SYSTEM_PROMPT) if style_key == "concise" else (self.REASONING_SYSTEM_PROMPT if reasoning else self.SYSTEM_PROMPT)
            # Tenta registry genérico para system
            alt = _load_prompt("system", "")
            if alt:
                base = alt

        extras: List[str] = []

        # 1) Preset de estilo — só adiciona se base não veio do registry já com estilo
        if style:
            key = style.strip().lower()
            # Se base já é flash/pro do registry, não duplica estilo
            is_registry_flash = "ESTILO CONCISO — LIMITE RÍGIDO" in base
            is_registry_pro = "ESTILO ANALISTA" in base
            if not ((key == "concise" and is_registry_flash) or (key == "analyst" and is_registry_pro)):
                preset = STYLE_PRESETS.get(key, "")
                if preset:
                    extras.append(preset)
                elif key != "default":
                    extras.append(f"ESTILO SOLICITADO: {style}")

        # 2) Instrução livre do chamante (Claude system / ChatGPT system message / Gemini systemInstruction)
        if custom_instructions and custom_instructions.strip():
            # Limita tamanho e isola para não sobrescrever regras críticas
            ci = custom_instructions.strip()[:2000]
            extras.append(
                "INSTRUÇÃO DO CHAMANTE (prioridade de estilo/comportamento, mas NUNCA invente dados além das evidências):\n"
                + ci
            )
            # Reforço de segurança — sempre após instrução custom
            extras.append(
                "Lembre-se: mesmo com instrução custom, NUNCA invente números/datas/fatos fora das evidências; "
                "se faltar dado, declare a lacuna."
            )

        # 3) Hint interno de reasoning
        if hint:
            extras.append(f"Instrução adicional para esta pergunta: {hint}")

        if extras:
            return base + "\n\n" + "\n\n".join(extras)
        return base

    def _extra_block(self, style: str = "", custom_instructions: str = "", hint: str = "") -> str:
        extras: List[str] = []
        if style:
            key = style.strip().lower()
            preset = STYLE_PRESETS.get(key, "")
            if preset:
                extras.append(preset)
            elif key != "default":
                extras.append(f"ESTILO SOLICITADO: {style}")
        if custom_instructions and custom_instructions.strip():
            ci = custom_instructions.strip()[:2000]
            extras.append(
                "INSTRUÇÃO DO CHAMANTE (prioridade de estilo/comportamento, mas NUNCA invente dados além das evidências):\n" + ci
            )
            extras.append(
                "Lembre-se: mesmo com instrução custom, NUNCA invente números/datas/fatos fora das evidências; se faltar dado, declare a lacuna."
            )
        if hint:
            extras.append(f"Instrução adicional para esta pergunta: {hint}")
        return "\n\n".join(extras)

    def build(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        mode: Mode = Mode.auto,
        reasoning: bool = False,
        reasoning_hint: str = "",
        style: str = "",
        custom_instructions: str = "",
    ) -> str:
        system = self._choose_system(reasoning, reasoning_hint, mode=mode, style=style, custom_instructions=custom_instructions)
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            base = f"{system}\n\n{evidence_section}\n\n"
        else:
            extra = self._extra_block(style=style, custom_instructions=custom_instructions, hint=reasoning_hint)
            if extra:
                base = f"{self.NO_EVIDENCE_PROMPT}\n\n{extra}\n\n"
            else:
                base = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        return f"{base}Pergunta: {question}\n\nResposta:"

    def build_with_history(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        history_context: str = "",
        mode: Mode = Mode.auto,
        reasoning: bool = False,
        reasoning_hint: str = "",
        style: str = "",
        custom_instructions: str = "",
    ) -> str:
        system = self._choose_system(reasoning, reasoning_hint, mode=mode, style=style, custom_instructions=custom_instructions)
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            prompt = f"{system}\n\n{evidence_section}\n\n"
        else:
            extra = self._extra_block(style=style, custom_instructions=custom_instructions, hint=reasoning_hint)
            if extra:
                prompt = f"{self.NO_EVIDENCE_PROMPT}\n\n{extra}\n\n"
            else:
                prompt = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"
        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt

    def build_reasoning(
        self,
        question: str,
        evidences: List[Evidence],
        reasoning_hint: str = "",
        history_context: str = "",
        style: str = "",
        custom_instructions: str = "",
    ) -> str:
        """Atalho para perguntas que exigem CoT: sempre usa REASONING_SYSTEM_PROMPT."""
        return self.build_with_history(
            question, evidences, history_context, reasoning=True, reasoning_hint=reasoning_hint,
            style=style, custom_instructions=custom_instructions,
        )