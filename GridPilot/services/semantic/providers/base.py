"""Abstract base class interface for semantic vector embedding providers."""
from __future__ import annotations

import abc
from typing import List


class BaseEmbeddingProvider(abc.ABC):
    """Decoupled interface wrapping text embedding engines."""

    @abc.abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate high-dimensional float vectors (typically 1536) for target text chunks."""
        pass

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Return target embedding model identifier name."""
        pass
