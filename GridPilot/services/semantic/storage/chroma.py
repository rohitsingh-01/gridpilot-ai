"""Concrete implementation of BaseSemanticStore using ChromaDB."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import os
import chromadb
from chromadb.api import ClientAPI

from services.semantic.storage.base import BaseSemanticStore


class ChromaStore(BaseSemanticStore):
    """SemanticStore wrapper for ChromaDB. Supports Ephemeral, Persistent, and HttpClient runtimes."""

    def __init__(self, client: Optional[ClientAPI] = None, host: str = "localhost", port: int = 8000) -> None:
        if client is not None:
            self._client = client
            return

        # Check if environment dictates persistent path
        persist_path = os.getenv("CHROMA_PERSISTENT_PATH", "data/chromadb")
        
        try:
            # Try HttpClient first
            self._client = chromadb.HttpClient(host=host, port=port)
            # Trigger a simple heartbeat check to verify if the server is actually running
            self._client.heartbeat()
        except Exception:
            # Fall back to local persistent store if host is down
            os.makedirs(persist_path, exist_ok=True)
            self._client = chromadb.PersistentClient(path=persist_path)

    async def initialize_collection(self, collection_name: str) -> None:
        # ChromaDB get_or_create_collection is synchronous
        self._client.get_or_create_collection(name=collection_name)

    async def upsert_chunks(
        self,
        collection_name: str,
        ids: List[str],
        vectors: List[List[float]],
        metadatas: List[Dict[str, Any]],
        contents: List[str],
    ) -> None:
        if not ids:
            return
        collection = self._client.get_collection(name=collection_name)
        # Chroma upsert is synchronous
        collection.upsert(
            ids=ids,
            embeddings=vectors,
            metadatas=metadatas,
            documents=contents
        )

    async def query_semantic(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        collection = self._client.get_collection(name=collection_name)
        
        # Format filters to match Chroma's where format if provided
        # Chroma where filter structure: {"metadata_field": "value"} or operators
        where_filter = filters if filters else None

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=limit,
            where=where_filter
        )

        output = []
        if results and "ids" in results and results["ids"] and len(results["ids"]) > 0:
            ids_list = results["ids"][0]
            docs_list = results["documents"][0] if results.get("documents") else [None] * len(ids_list)
            metas_list = results["metadatas"][0] if results.get("metadatas") else [None] * len(ids_list)
            dists_list = results["distances"][0] if results.get("distances") else [None] * len(ids_list)

            for idx in range(len(ids_list)):
                output.append({
                    "id": ids_list[idx],
                    "content": docs_list[idx],
                    "metadata": metas_list[idx],
                    "distance": dists_list[idx]
                })
        return output

    async def delete_chunks(self, collection_name: str, ids: List[str]) -> None:
        if not ids:
            return
        collection = self._client.get_collection(name=collection_name)
        collection.delete(ids=ids)

    async def get_collection_metadata(self, collection_name: str) -> List[Dict[str, Any]]:
        collection = self._client.get_collection(name=collection_name)
        data = collection.get(include=["metadatas"])
        
        output = []
        if data and "ids" in data:
            ids = data["ids"]
            metas = data["metadatas"] if data.get("metadatas") else [None] * len(ids)
            for idx in range(len(ids)):
                output.append({
                    "id": ids[idx],
                    "metadata": metas[idx]
                })
        return output
