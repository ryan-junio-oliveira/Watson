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

def test_non_image_question_filters_image_low_score():
    """Pergunta não-imagem (champions) não deve usar imagem com score baixo."""
    bot, retr, oll = make_bot([fake_image_evidence(score=0.2)], ollama_answer="Não encontrei")
    resp = bot.ask("quais são os times do pote 1 da champions league")
    # Nova lógica filtra image-only low relevance para não-imagem → cai em no_documents
    assert resp.metadata.get("fallback") == "no_documents" or not resp.evidences or all(e.metadata.get("source_type") != "image" for e in resp.evidences), \
        f"Deveria filtrar imagem irrelevante, evidences={resp.evidences}, meta={resp.metadata}"
    print("PASS: champions filtra imagem irrelevante")

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
    test_non_image_question_filters_image_low_score()
    test_factual_with_image_and_text_keeps_text()
    test_greeting_not_use_image()
    test_descreva_imagem_uses_image()
    print("\nTodos os testes de imagem passaram!")
