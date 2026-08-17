"""Teste e2e completo: PDF -> indexação -> retrieval -> rerank -> LLM (§32, §37).

Verifica o critério de sucesso: para um problema técnico específico, o sistema
recupera o trecho correto do manual correto (fabricante, modelo, seção, página)
e o LLM responde com base nesse manual.

Uso:
    python tests/e2e_manual.py [--question "pergunta"] [--top-k 5]

Sem --question, roda uma bateria de perguntas padrão e imprime as respostas.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Usa o modelo de embeddings já baixado em cache (sem revalidar via rede).
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import config  # noqa: E402
from ingestion.embeddings import EmbeddingGenerator  # noqa: E402
from llm.ollama_client import OllamaClient  # noqa: E402
from rag.prompt import PromptBuilder  # noqa: E402
from rag.retriever import Retriever  # noqa: E402
from rag.reranker import Reranker as RagReranker  # noqa: E402

DEFAULT_QUESTIONS = [
    "Como desatolar papel preso na bandeja da impressora?",
    "Como substituir o cartucho de toner da E52645?",
    "Como configurar a rede sem fio da impressora?",
    "Como imprimir em frente e verso (duplex)?",
    "Como limpar a impressora e a área do toner?",
]


def build_chat():
    emb = EmbeddingGenerator(
        model_name=config.embedding_model, device=config.embedding_device
    )
    retriever = Retriever(
        embedding_generator=emb,
        chroma_persist_dir=config.vector_db_dir,
        top_k=config.top_k,
        similarity_threshold=config.similarity_threshold,
    )
    prompt = PromptBuilder()
    llm = OllamaClient(
        model=config.ollama_model,
        base_url=config.ollama_base_url,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        request_timeout=config.ollama_timeout,
    )
    reranker = (
        RagReranker(model_name=config.reranker_model, device=config.embedding_device)
        if config.use_reranker
        else None
    )
    return emb, retriever, prompt, llm, reranker


def answer(question: str, top_k: int, chat) -> None:
    _, retriever, prompt, llm, reranker = chat
    docs = retriever.retrieve(question)
    if reranker and docs:
        docs = reranker.rerank(question, docs, top_k=len(docs))

    print("=" * 70)
    print(f"PERGUNTA: {question}")
    if not docs:
        print("  (nenhum documento recuperado)")
        return

    from rag.evidence import EvidenceNormalizer

    evidences = [EvidenceNormalizer.from_chroma_document(d) for d in docs[:top_k]]
    print("--- Evidências recuperadas (trechos usados pelo LLM) ---")
    for ev in evidences:
        print(f"  [{ev.score:.3f}] {ev.title} | {ev.context_label}")
        print(f"       {ev.content[:120].replace(chr(10), ' ')}")

    p = prompt.build(question, evidences, mode="rag")
    print("--- RESPOSTA DO LLM (com base no manual) ---")
    answer_text = llm.ask(p)
    print(answer_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", type=str, default=None)
    parser.add_argument("--top-k", type=int, default=config.top_k)
    args = parser.parse_args()

    chat = build_chat()  # reutiliza o retriever/modelo entre perguntas
    questions = [args.question] if args.question else DEFAULT_QUESTIONS
    for q in questions:
        answer(q, args.top_k, chat)
    return 0


if __name__ == "__main__":
    sys.exit(main())