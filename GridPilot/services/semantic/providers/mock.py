"""Mock implementation of BaseEmbeddingProvider returning deterministic unit-normalized float vectors offline."""
from __future__ import annotations

import hashlib
import random
from typing import List

from services.semantic.providers.base import BaseEmbeddingProvider


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Offline embedding provider that generates deterministic vectors of size 1536 without network calls."""

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            # Deterministic hash of the input text
            h = hashlib.sha256(text.encode("utf-8")).digest()
            # Seed random generator with the hash
            seed = int.from_bytes(h[:8], byteorder="big")
            rng = random.Random(seed)
            # Generate 1536-dimensional raw values
            vector = [rng.uniform(-1.0, 1.0) for _ in range(1536)]
            # Normalize vector to unit length (L2 norm) for cosine similarity
            norm = sum(val * val for val in vector) ** 0.5
            if norm > 0:
                normalized = [val / norm for val in vector]
            else:
                normalized = [0.0] * 1536
            results.append(normalized)
        return results

    @property
    def model_name(self) -> str:
        return "mock-embedding-v3"
