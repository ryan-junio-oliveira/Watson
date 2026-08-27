from typing import List, Optional

from rag.evidence import Evidence
from rag.response import Mode


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é o Watson, um analista meticuloso que assessora um detetive. "
        "Sua função é analisar os dados fornecidos, cruzar informações, tirar "
        "conclusões e responder com clareza, naturalidade e precisão.\n"
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
        "5. Responda em português de forma conversacional e natural, como um "
        "analista explicando a um colega — não repita trechos literais dos "
        "documentos e evite 'spam' de tópicos quando uma frase resolve.\n"
        "6. Quando a pergunta pedir um procedimento ou passos, liste TODOS os "
        "passos na ordem correta, sem omitir nem pular etapas numeradas.\n"
        "7. Se houver contradição entre fontes, aponte as diferentes versões.\n"
        "8. Se a informação estiver incompleta, diga o que foi encontrado, o "
        "que falta e sugira como obtê-la.\n"
        "9. Ao final, se as evidências tiverem seção/página reais, cite-as "
        "(ex.: 'Fonte: seção X, página Y'). Para dados de banco (formato "
        "'campo: valor'), não invente seção/página.\n"
        "10. Conclua respondendo diretamente à pergunta e, quando útil, "
        "acrescente o contexto que justifica a conclusão."
    )

    REASONING_SYSTEM_PROMPT = (
        "Você é o Watson, um analista sênior que assessora um detetive. "
        "Resolva a pergunta com raciocínio estruturado e verificável.\n"
        "Processo obrigatório (pense passo a passo internamente, mas NÃO exponha o rascunho — entregue só a resposta final bem formatada):\n"
        "1. COMPREENSÃO: reformule o que foi pedido e identifique o tipo de operação (factual, comparação, percentual, soma, média, tendência, listagem).\n"
        "2. EVIDÊNCIAS: selecione apenas os trechos que sustentam a resposta; descarte ruído. Se faltar dado, declare a lacuna.\n"
        "3. RACIOCÍNIO: para cálculos, execute a conta literalmente (ex.: (22-15)/15*100=46,7%) e valide a ordem de grandeza; para comparações, monte tabela lado a lado; para tendências, descreva direção e magnitude.\n"
        "4. VERIFICAÇÃO: cheque contradições entre fontes; se houver, apresente as duas versões. Confirme que todo número citado existe nas evidências.\n"
        "5. SÍNTESE: responda direto à pergunta nas primeiras 2 frases, depois detalhe com contexto, sempre citando seção/página quando houver. Se inferir algo, marque como '(inferência)'.\n"
        "Regras: nunca invente dados; cruze fontes quando útil; para procedimentos liste TODOS os passos; seja conciso mas completo; português natural.\n"
        "Formato de citação: 'Fonte: <arquivo> — seção X, pág. Y' ou 'Fonte: cálculo verificado' quando vier de conta determinística."
    )

    NO_EVIDENCE_PROMPT = (
        "Você é o Watson, um analista meticuloso que trabalha com uma base "
        "de conhecimento indexada.\n"
        "Não foram encontradas informações relevantes no índice para "
        "responder à pergunta.\n"
        "Siga estas regras:\n"
        "1. Seja honesto: informe que não encontrou dados específicos no "
        "acervo indexado.\n"
        "2. NÃO invente informações — não fabrique números, datas ou fatos.\n"
        "3. Ajude o usuário: sugira reformulações da pergunta ou verificar se "
        "os documentos pertinentes foram indexados.\n"
        "4. Se houver conteúdo no acervo que possa ser útil ao tema, "
        "mencione brevemente o que existe.\n"
        "5. Responda em português, de forma natural, objetiva e útil."
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

    def _choose_system(self, reasoning: bool = False, hint: str = "") -> str:
        base = self.REASONING_SYSTEM_PROMPT if reasoning else self.SYSTEM_PROMPT
        if hint:
            return f"{base}\n\nInstrução adicional para esta pergunta: {hint}"
        return base

    def build(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        mode: Mode = Mode.auto,
        reasoning: bool = False,
        reasoning_hint: str = "",
    ) -> str:
        system = self._choose_system(reasoning, reasoning_hint)
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            base = f"{system}\n\n{evidence_section}\n\n"
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
    ) -> str:
        system = self._choose_system(reasoning, reasoning_hint)
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            prompt = f"{system}\n\n{evidence_section}\n\n"
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
    ) -> str:
        """Atalho para perguntas que exigem CoT: sempre usa REASONING_SYSTEM_PROMPT."""
        return self.build_with_history(
            question, evidences, history_context, reasoning=True, reasoning_hint=reasoning_hint
        )