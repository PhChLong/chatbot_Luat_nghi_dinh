from typing import Any

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class Reranker:
    def __init__(self, name="AITeamVN/Vietnamese_Reranker", device="cuda", max_length:int = 1024):
        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForSequenceClassification.from_pretrained(name).to(device).eval()
        self.device = device
        self.max_length = max_length

    @torch.inference_mode()
    def rerank(self, query: str, docs: list[dict[str, Any]], top_k: int = 5) -> list[tuple[dict[str, Any], float]]:
        """
        rerank sẽ nhận input là các chunks được tìm thấy bằng query đơn giản
        """
        pairs = [[query, d['content']] for d in docs]
        inputs = self.tok(pairs, padding=True, truncation=True,
                          max_length=self.max_length, return_tensors="pt").to(self.device)
        scores:list[float] = self.model(**inputs).logits.view(-1).float().cpu().tolist()
        ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]