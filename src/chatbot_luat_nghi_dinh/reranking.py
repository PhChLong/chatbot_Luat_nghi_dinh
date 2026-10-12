from abc import ABC, abstractmethod
from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Reranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, docs: list[dict[str, Any]], top_k: int = 5
    ) -> list[tuple[dict[str, Any], float]]:
        raise NotImplementedError


class AITeamVNReranker(Reranker):
    def __init__(self, device="cuda", max_length: int = 1024):
        self.name = "AITeamVN/Vietnamese_Reranker"
        self.tok = AutoTokenizer.from_pretrained(self.name)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(self.name)
            .to(device)
            .eval()
        )
        self.device = device
        self.max_length = max_length

    @torch.inference_mode()
    def rerank(
        self, query: str, docs: list[dict[str, Any]], top_k: int = 5
    ) -> list[tuple[dict[str, Any], float]]:
        """
        rerank sẽ nhận input là các chunks được tìm thấy bằng query đơn giản
        """
        pairs = [[query, d["content"]] for d in docs]
        inputs = self.tok(
            pairs,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        scores: list[float] = (
            self.model(**inputs).logits.view(-1).float().cpu().tolist()
        )
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


class ProxyAITeamVNReranker(Reranker):
    def __init__(self, device="cuda", max_length: int = 1024) -> None:
        self.device = device
        self.max_length = max_length
        self._real_reranker: AITeamVNReranker | None = None

    def rerank(
        self, query: str, docs: list[dict[str, Any]], top_k: int = 5
    ) -> list[tuple[dict[str, Any], float]]:
        if self._real_reranker is None:
            self._real_reranker = AITeamVNReranker(
                device=self.device, max_length=self.max_length
            )
        return self._real_reranker.rerank(query=query, docs=docs, top_k=top_k)
