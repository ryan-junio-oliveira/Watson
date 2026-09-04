"""Eval RAG simples — mede recall de sources e keywords sem LLM-as-judge (RAGAS pode ser adicionado).
Uso: python tests/eval/run_eval.py
"""
import json
import pathlib
import sys

# Adiciona root ao path
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.config import Config

GOLDEN = ROOT / "tests/eval/golden.jsonl"

def normalize(s: str) -> str:
    return (s or "").lower()

def eval_once(question: str, mode: str, profile: str, keywords, expected_sources):
    from core.factories import build_chatbot
    cfg = Config()
    # Força perfil por request via env temporário
    import os
    os.environ["WATSON_PROFILE"] = profile
    # Recarrega config para perfil
    import importlib
    import core.config as cfg_mod
    importlib.reload(cfg_mod)
    cfg = cfg_mod.Config()
    from unittest.mock import patch
    # Build chatbot leve (sem preload de modelos pesados se possível)
    # Para CI, usamos o chatbot real mas com timeout curto
    try:
        from core.factories import build_chatbot as _bc
        import logging
        logger = logging.getLogger("eval")
        bot = _bc(cfg, logger)
        # Usa modo não-stream
        from rag.response import Mode
        m = Mode(mode) if mode in ("rag", "web", "auto") else Mode.auto
        # Chama _prepare_evidence para medir recall sem LLM
        evs = bot._prepare_evidence(question, profile=profile)
        sources = [e.source or e.title for e in evs]
        # Também testa geração curta se houver docs
        # Para evitar LLM lento em CI, checa só recall
        hit = any(any(exp.lower() in s.lower() for s in sources) for exp in expected_sources) if expected_sources else True
        kw_hit = all(k.lower() in " ".join([e.content for e in evs]).lower() for k in keywords) if keywords else True
        return {"hit": hit, "kw_hit": kw_hit, "sources": sources[:3], "evidence_count": len(evs)}
    except Exception as e:
        return {"hit": False, "kw_hit": False, "error": str(e)[:300]}

def main():
    if not GOLDEN.exists():
        print(f"Golden não encontrado: {GOLDEN}")
        sys.exit(1)
    total = 0
    passed = 0
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        total += 1
        rec = json.loads(line)
        q = rec["question"]
        res = eval_once(q, rec.get("mode", "rag"), rec.get("profile", "flash"), rec.get("keywords", []), rec.get("expected_sources", []))
        ok = res.get("hit") and res.get("kw_hit")
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"[{status}] {q[:60]} — hit={res.get('hit')} kw={res.get('kw_hit')} ev={res.get('evidence_count')} src={res.get('sources')} {res.get('error','')[:100]}")
    print(f"\nEval: {passed}/{total} passou ({passed/total*100:.1f}%)")
    sys.exit(0 if passed/total >= 0.6 else 1)

if __name__ == "__main__":
    main()
