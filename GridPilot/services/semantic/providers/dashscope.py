"""Concrete implementation of BaseEmbeddingProvider using Alibaba Cloud DashScope TextEmbedding API."""
from __future__ import annotations

import os
from typing import List, Optional
import dashscope
from dashscope import TextEmbedding

from services.semantic.providers.base import BaseEmbeddingProvider


class DashScopeEmbeddingProvider(BaseEmbeddingProvider):
    """Generates 1536-dimensional embeddings using DashScope's text-embedding-v3 model."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self._api_key:
            # We don't crash on init to allow instantiation, but we will warn or crash on call
            pass

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not self._api_key:
            raise ValueError("DASHSCOPE_API_KEY environment variable is not set.")

        # dashscope SDK expects either a single string or list of strings
        # We call the synchronous SDK method (run in executor/blocking thread or simply call directly since it is fast)
        # To avoid blocking, we can call it directly or run it under an executor if needed.
        # Calling directly:
        response = TextEmbedding.call(
            model=TextEmbedding.Models.text_embedding_v3,
            input=texts,
            api_key=self._api_key
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"DashScope embedding API call failed: Code {response.code}, Message: {response.message}"
            )

        embeddings = [item["embedding"] for item in response.output["embeddings"]]
        return embeddings

    @property
    def model_name(self) -> str:
        return "text-embedding-v3"
