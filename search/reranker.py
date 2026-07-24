import logging
from typing import List, Optional

from rag.evidence import Evidence


class Reranker:
    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str = "cpu",
        logger: Optional[logging.Logger] = None,
    ):
        self.model_name = model_name
        self.device = device
        self.logger = logger
        self._model = None

    def _load_model(self):
        if self._model is None:
            if self.logger:
                self.logger.info(f"Loading reranker model: {self.model_name}")
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device=self.device)
        return self._model

    def rerank(
        self,
        query: str,
        evidences: List[Evidence],
        top_k: Optional[int] = None,
    ) -> List[Evidence]:
        if not evidences:
            return []

        model = self._load_model()
        if top_k is None:
            top_k = len(evidences)

        pairs = [[query, ev.content[:2000]] for ev in evidences]
        scores = model.predict(pairs)

        scored: List[tuple] = list(zip(scores, evidences))
        scored.sort(key=lambda x: x[0], reverse=True)

        result: List[Evidence] = []
        for score, ev in scored[:top_k]:
            ev.score = round(float(score), 4)
            result.append(ev)

        if self.logger:
            top_score = round(float(scored[0][0]), 4) if scored else 0
            self.logger.info(
                f"Reranked {len(evidences)} evidences -> kept {len(result)} "
                f"(top score: {top_score})"
            )

        return result
