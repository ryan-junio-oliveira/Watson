from typing import List, Optional

from rag.evidence import Evidence
from rag.response import Mode


class PromptBuilder:
    SYSTEM_PROMPT = (
        "Você é um assistente especializado em responder perguntas.\n"
        "Siga estas regras:\n"
        "1. Quando houver evidências fornecidas, responda APENAS com base "
        "nelas. Cite a fonte entre colchetes, "
        "ex: [https://www.site.com.br/artigo] ou [Documento: arquivo.txt].\n"
        "2. NUNCA invente informações falsas — se as evidências não "
        "contiverem a resposta, diga que não encontrou.\n"
        "3. Se houver contradição entre fontes, aponte as diferentes "
        "versões.\n"
        "4. Se a informação estiver incompleta, indique o que foi "
        "encontrado e o que ainda falta.\n"
        "5. Responda em português.\n"
        "6. Seja objetivo, direto e prefira tópicos quando apropriado."
    )

    NO_EVIDENCE_PROMPT = (
        "Você é um assistente útil.\n"
        "Não foram encontradas evidências específicas (documentos internos "
        "ou resultados de pesquisa na internet) para responder à pergunta.\n"
        "Siga estas regras:\n"
        "1. Se a pergunta for sobre conhecimento geral, raciocínio lógico, "
        "matemática básica, definições de dicionário, ortografia, ou "
        "qualquer tópico que não exija fontes externas, responda "
        "normalmente com seu conhecimento.\n"
        "2. Se a pergunta exigir informações específicas sobre os "
        "documentos ou dados do sistema, informe que não foi possível "
        "encontrar a resposta e sugira reformular ou fornecer mais "
        "detalhes.\n"
        "3. Seja honesto: se você sabe a resposta com segurança, "
        "responda. Se não tem certeza, indique sua limitação.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto."
    )

    NO_EVIDENCE_STRICT = (
        "Você é um assistente especializado em responder perguntas.\n"
        "O modo de consulta selecionado ({mode}) busca APENAS em "
        "{source}, mas nenhum resultado relevante foi encontrado.\n"
        "Siga estas regras:\n"
        "1. Informe ao usuário que não foram encontrados resultados "
        "na fonte especificada.\n"
        "2. NÃO utilize seu conhecimento interno para responder — "
        "a resposta deve se limitar ao que foi encontrado na fonte.\n"
        "3. Sugira ao usuário tentar outro modo de consulta ou "
        "reformular a pergunta.\n"
        "4. Responda em português.\n"
        "5. Seja objetivo e direto."
    )

    MODE_LABELS = {
        Mode.rag: ("documentos internos", "documentos internos"),
        Mode.web: ("resultados de pesquisa na internet", "internet"),
        Mode.all: ("documentos internos e internet", "ambas as fontes"),
    }

    @staticmethod
    def _format_evidence_block(ev: Evidence) -> str:
        block = f"============================\n"
        if ev.url:
            block += f"Fonte: {ev.url}\n"
        elif ev.source:
            block += f"Fonte: {ev.source}\n"
        if ev.title:
            block += f"Título: {ev.title}\n"
        block += f"\n{ev.content}\n"
        return block

    def build(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        mode: Mode = Mode.auto,
    ) -> str:
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            base = f"{self.SYSTEM_PROMPT}\n\n{evidence_section}\n\n"
        elif mode == Mode.knowledge:
            base = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        elif mode in self.MODE_LABELS:
            src_label, _ = self.MODE_LABELS[mode]
            base = f"{self.NO_EVIDENCE_STRICT.format(mode=mode.value, source=src_label)}\n\n"
        else:
            base = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        return f"{base}Pergunta: {question}\n\nResposta:"

    def build_with_history(
        self,
        question: str,
        evidences: Optional[List[Evidence]] = None,
        history_context: str = "",
        mode: Mode = Mode.auto,
    ) -> str:
        if evidences:
            blocks = [self._format_evidence_block(ev) for ev in evidences]
            evidence_section = "Evidências:\n\n" + "\n\n".join(blocks)
            prompt = f"{self.SYSTEM_PROMPT}\n\n{evidence_section}\n\n"
        elif mode == Mode.knowledge:
            prompt = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        elif mode in self.MODE_LABELS:
            src_label, _ = self.MODE_LABELS[mode]
            prompt = f"{self.NO_EVIDENCE_STRICT.format(mode=mode.value, source=src_label)}\n\n"
        else:
            prompt = f"{self.NO_EVIDENCE_PROMPT}\n\n"
        if history_context:
            prompt += f"Histórico da conversa:\n{history_context}\n\n"
        prompt += f"Pergunta: {question}\n\nResposta:"
        return prompt
