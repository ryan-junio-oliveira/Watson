"""Testes para perguntas sobre imagem — verifica se RAG usa imagem corretamente."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import types
from unittest.mock import MagicMock

# Mock pesados antes de importar chatbot
for mod in ["langchain_core", "langchain_core.documents", "langchain_chroma", "chromadb", "sentence_transformers", "tqdm", "pymupdf", "pymupdf4llm", "pytesseract", "PIL"]:
    sys.modules.setdefault(mod, MagicMock())
# Document mock
class _Doc:
    def __init__(self, page_content="", metadata=None):
        self.page_content = page_content
        self.metadata = metadata or {}
from unittest.mock import MagicMock as _MM
sys.modules["langchain_core.documents"].Document = _Doc

from rag.chatbot import ChatBot
from rag.prompt import PromptBuilder
from rag.evidence import Evidence
Document = _Doc


def make_bot(retriever_returns, ollama_answer="Resposta simulada"):
    retr = MagicMock()
    retr.top_k = 5
    retr.similarity_threshold = None
    retr.retrieve.return_value = retriever_returns
    retr.retrieve_all_from_source.return_value = []
    prompt = PromptBuilder()
    oll = MagicMock()
    oll.temperature = 0.1
    oll.max_tokens = 2048
    oll.model = "gemma3:4b"
    oll.supports_thinking.return_value = False
    oll.ask.return_value = ollama_answer
    oll._strip_thinking.side_effect = lambda x: x
    oll.ask_stream.return_value = iter([ollama_answer])
    return ChatBot(retriever=retr, prompt_builder=prompt, ollama_client=oll, enable_reasoning=False), retr, oll


def fake_image_evidence(content="Imagem sem texto detectado: images.jpg\n[Descrição da imagem: diagrama técnico]", score=0.2):
    return Document(
        page_content=content,
        metadata={"source": "documents/images.jpg", "filename": "images.jpg", "chunk_id": "img1", "source_type": "image", "relevance_score": score}
    )

def fake_text_evidence(content="Manual HP LaserJet E52645: erro E123", score=0.85):
    return Document(
        page_content=content,
        metadata={"source": "documents/manual.pdf", "filename": "manual.pdf", "chunk_id": "c2", "source_type": "pdf", "relevance_score": score}
    )

def test_image_question_uses_image_even_with_low_score():
    """Pergunta sobre imagem deve usar evidência de imagem mesmo com score baixo (0.2)."""
    bot, retr, oll = make_bot([fake_image_evidence(score=0.2)], ollama_answer="Na imagem há um diagrama técnico.")
    # Pergunta contém 'imagem' → is_image_question True, não deve filtrar
    resp = bot.ask("o que tem na imagem?")
    assert resp.evidences, "Deveria manter evidência de imagem para pergunta sobre imagem"
    assert any(e.metadata.get("source_type") == "image" for e in resp.evidences), "Evidência de imagem deveria estar presente"
    print("PASS: imagem question usa imagem com score baixo")

def test_non_image_question_filters_generic_image_low_score():
    """Imagem genérica (sem champions) não deve ser usada para pergunta champions com score baixo."""
    bot, retr, oll = make_bot([fake_image_evidence(content="Imagem sem texto: paisagem", score=0.2)], ollama_answer="Não encontrei")
    resp = bot.ask("quais são os times do pote 1 da champions league")
    assert resp.metadata.get("fallback") == "no_documents" or not resp.evidences, \
        f"Deveria filtrar imagem genérica irrelevante, evidences={resp.evidences}, meta={resp.metadata}"
    print("PASS: champions filtra imagem genérica irrelevante")

def test_champions_image_high_relevance_kept():
    """Imagem com potes da Champions DEVE ser usada para pergunta sobre pote 1 (mesmo sem dizer 'imagem')."""
    champions_content = "Pote 1: Real Madrid, Manchester City, Bayern Munich, PSG, Inter, Dortmund, Barcelona, Liverpool"
    bot, retr, oll = make_bot([fake_image_evidence(content=champions_content, score=0.75)], ollama_answer="Com base na imagem, Pote 1: Real Madrid...")
    resp = bot.ask("quais são os times do pote 1 da champions league")
    assert resp.evidences, "Imagem com champions deve ser mantida (content overlap + score alto)"
    assert any("champions" in e.content.lower() or "pote" in e.content.lower() for e in resp.evidences), "Evidência deve conter champions/pote"
    print("PASS: champions com imagem de potes é mantida (score alto + overlap)")

def test_champions_image_low_score_but_overlap_kept():
    """Mesmo com score baixo, se imagem contém 'champions/pote' e pergunta também, mantém (content_overlap)."""
    champions_content = "Pote 1 - Times da Champions League distribuídos"
    bot, retr, oll = make_bot([fake_image_evidence(content=champions_content, score=0.2)], ollama_answer="Com base na imagem...")
    resp = bot.ask("quais são os times do pote 1 da champions league")
    # Com overlap, mesmo score baixo não é filtrado
    assert resp.evidences, "Com overlap, não deve filtrar mesmo com score baixo"
    print("PASS: champions com overlap mantém mesmo com score baixo")

def test_factual_with_image_and_text_keeps_text():
    """Se há imagem e texto, pergunta factual deve priorizar texto de alta relevância."""
    bot, retr, oll = make_bot([fake_image_evidence(score=0.2), fake_text_evidence(score=0.85)], ollama_answer="Erro E123 está no manual.")
    resp = bot.ask("como corrigir erro E123 na HP E52645?")
    assert resp.evidences, "Deveria ter evidência"
    # Deve conter o texto de alta relevância (pdf)
    assert any(e.metadata.get("source_type") == "pdf" for e in resp.evidences), f"Deveria conter pdf, evidences={[e.metadata for e in resp.evidences]}"
    print("PASS: factual com imagem+texto mantém texto relevante")

def test_greeting_not_use_image():
    bot, retr, oll = make_bot([fake_image_evidence(score=0.9)], ollama_answer="Olá")
    resp = bot.ask("bom dia")
    assert resp.metadata.get("provider") == "greeting"
    assert not retr.retrieve.called, "Saudação não deve chamar retriever"
    print("PASS: saudação não usa imagem")

def test_descreva_imagem_uses_image():
    bot, retr, oll = make_bot([fake_image_evidence(content="Texto da imagem: Nota Fiscal R$ 150", score=0.25)], ollama_answer="A imagem contém Nota Fiscal")
    for q in ["descreva a imagem", "qual o texto da imagem?", "o que tem na foto?"]:
        resp = bot.ask(q)
        assert resp.evidences, f"Pergunta '{q}' deveria usar imagem"
        print(f"PASS: '{q}' usa imagem")

if __name__ == "__main__":
    test_image_question_uses_image_even_with_low_score()
    test_non_image_question_filters_generic_image_low_score()
    test_champions_image_high_relevance_kept()
    test_champions_image_low_score_but_overlap_kept()
    test_factual_with_image_and_text_keeps_text()
    test_greeting_not_use_image()
    test_descreva_imagem_uses_image()
    print("\nTodos os testes de imagem passaram!")
