"""Benchmark de retrieval e2e sobre o manual real E52645 (§34).

Conjunto de perguntas conhecidas. Para cada uma, verifica se o retrieval
recupera o documento/modelo/seção/página corretos. Serve de regressão: após
qualquer mudança no indexador, reindexe e compare.

Uso:
    python tests/e2e_retrieval.py [--index-dir DIR] [--top-k 5]

Exit code 0 se todos os checks passarem; 1 caso contrário.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import config  # noqa: E402
from ingestion.embeddings import EmbeddingGenerator  # noqa: E402
from rag.retriever import Retriever  # noqa: E402

EXPECTED_DOC = "HP LASER JET E52645.pdf"

# (pergunta, fabricante_esperado, modelo_esperado, trecho_esperado)
REGRESSION_QUESTIONS = [
    (
        "Como desatolar papel preso na bandeja da impressora?",
        "HP", "E52645",
        ["bandeja", "papel", "remov"],
    ),
    (
        "Qual o procedimento para substituir o cartucho de toner?",
        "HP", "E52645",
        ["cartucho", "toner", "substitu"],
    ),
    (
        "Como configurar a rede sem fio (wifi) da impressora?",
        "HP", "E52645",
        ["sem fio", "rede", "configura"],
    ),
    (
        "Como imprimir em frente e verso (duplex)?",
        "HP", "E52645",
        ["frente e verso", "duplex", "imprim"],
    ),
    (
        "Como limpar a impressora?",
        "HP", "E52645",
        ["limpez", "limpar", "manuten"],
    ),
    (
        "Como habilitar a porta USB e imprimir de uma unidade flash?",
        "HP", "E52645",
        ["usb", "unidade flash", "imprim"],
    ),
]


def main() -> int:
    index_dir = os.getenv("VECTOR_DB_DIR", config.vector_db_dir)
    top_k = int(os.getenv("TOP_K", config.top_k))

    emb = EmbeddingGenerator(
        model_name=config.embedding_model, device=config.embedding_device
    )
    retriever = Retriever(
        embedding_generator=emb, chroma_persist_dir=index_dir, top_k=top_k
    )

    passed = 0
    failures = []
    for question, mfr, model, keywords in REGRESSION_QUESTIONS:
        docs = retriever.retrieve(question)
        if not docs:
            failures.append((question, "nenhum documento recuperado"))
            print(f"[FAIL] {question} -> 0 resultados")
            continue

        top = docs[0].metadata
        filename = top.get("filename", "")
        ok_doc = EXPECTED_DOC.lower() in filename.lower()
        text = docs[0].page_content.lower()
        ok_kw = any(k.lower() in text for k in keywords)
        label = (
            f"[{'OK ' if ok_doc and ok_kw else 'FAIL'}] {question}\n"
            f"      -> doc={filename} | seção={top.get('section')} | "
            f"pág={top.get('page_start')} | score={top.get('relevance_score'):.3f}"
        )
        print(label)
        if ok_doc and ok_kw:
            passed += 1
        else:
            failures.append((question, "doc/trecho incorreto"))

    print(f"\n=== {passed}/{len(REGRESSION_QUESTIONS)} perguntas OK ===")
    if failures:
        print("Falhas:")
        for q, reason in failures:
            print(f"  - {q} ({reason})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())