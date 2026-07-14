"""Abstract base class interface for semantic vector database storage engines."""
from __future__ import annotations

import abc
from typing import List, Dict, Any, Optional


class BaseSemanticStore(abc.ABC):
    """Decoupled interface wrapping vector databases (such as ChromaDB)."""

    @abc.abstractmethod
    async def initialize_collection(self, collection_name: str) -> None:
        """Create or configure a named collection, ensuring existence."""
        pass

    @abc.abstractmethod
    async def upsert_chunks(
        self,
        collection_name: str,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: List[Dict[str, Any]],
        contents: List[str],
    ) -> None:
        """Insert or update text chunks, embeddings, and metadata fields in bulk."""
        pass

    @abc.abstractmethod
    async def query_semantic(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Perform similarity search and return nearest chunks matching optional filters."""
        pass

    @abc.abstractmethod
    async def delete_chunks(self, collection_name: str, ids: List[str]) -> None:
        """Remove target chunk IDs from the vector collection."""
        pass

    @abc.abstractmethod
    async def get_collection_metadata(self, collection_name: str) -> List[Dict[str, Any]]:
        """Retrieve metadata for all registered chunks inside a collection (useful for index syncing)."""
        pass
