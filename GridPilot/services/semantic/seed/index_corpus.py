"""Coordinating CLI indexer for the semantic memory corpora ingestion pipeline."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import yaml
from pydantic import ValidationError

from services.semantic.models.schemas import ManifestModel, ManifestMetrics
from services.semantic.chunking.chunker import parse_markdown_document, generate_document_chunks, DocumentChunk
from services.semantic.providers.base import BaseEmbeddingProvider
from services.semantic.providers.dashscope import DashScopeEmbeddingProvider
from services.semantic.providers.mock import MockEmbeddingProvider
from services.semantic.storage.base import BaseSemanticStore
from services.semantic.storage.chroma import ChromaStore


class StructuredLogger:
    """JSON structured logger for the indexing pipeline."""

    def __init__(self, name: str = "gridpilot.semantic") -> None:
        self.name = name

    def log(self, level: str, phase: str, message: str, **metadata: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "logger": self.name,
            "phase": phase,
            "message": message,
            **metadata,
        }
        sys.stdout.write(json.dumps(record) + "\n")
        sys.stdout.flush()

    def info(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("info", phase, message, **metadata)

    def warning(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("warning", phase, message, **metadata)

    def error(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("error", phase, message, **metadata)


logger = StructuredLogger()


async def index_corpus_folder(
    corpus_name: str,
    folder_path: str,
    collection_name: str,
    provider: BaseEmbeddingProvider,
    store: BaseSemanticStore,
    batch_size: int = 32,
    force: bool = False,
) -> Dict[str, Any]:
    """Ingest, validate, chunk, and index all markdown documents in a target folder."""
    logger.info("index.start", f"Index run starting for corpus '{corpus_name}' -> collection '{collection_name}'", corpus=corpus_name)
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path, exist_ok=True)
        logger.info("index.folder_created", f"Created empty corpus folder: {folder_path}", path=folder_path)
        return {"documents": 0, "chunks": 0, "vectors_inserted": 0, "pruned": 0}

    # Initialize store collection
    await store.initialize_collection(collection_name)

    # 1. Discover local files
    md_files = [
        os.path.join(folder_path, f)
        for f in os.listdir(folder_path)
        if f.lower().endswith(".md")
    ]

    if not md_files:
        logger.info("index.empty", f"No markdown documents found in {folder_path}.", path=folder_path)
        existing_records = await store.get_collection_metadata(collection_name)
        obsolete_ids = [rec["id"] for rec in existing_records]
        if obsolete_ids:
            logger.info("index.pruning", f"Pruning all {len(obsolete_ids)} obsolete vector chunks from empty folder.", count=len(obsolete_ids))
            await store.delete_chunks(collection_name, obsolete_ids)
        return {"documents": 0, "chunks": 0, "vectors_inserted": 0, "pruned": len(obsolete_ids)}

    # 2. Load existing collection index metadata for idempotency checks
    existing_records = await store.get_collection_metadata(collection_name)
    existing_checksums = {}  # chunk_id -> checksum
    for rec in existing_records:
        cid = rec["id"]
        meta = rec.get("metadata") or {}
        if "checksum" in meta:
            existing_checksums[cid] = meta["checksum"]

    active_chunk_ids = set()
    chunks_to_embed: List[DocumentChunk] = []
    
    doc_count = 0
    total_chunk_count = 0

    # Processing provenance timestamps
    ingested_time_str = datetime.now(timezone.utc).isoformat()
    processing_ver = "1.0.0"
    pipeline_ver = "1.0.0"

    # 3. Parse and chunk documents
    for file_path in md_files:
        try:
            meta, body = parse_markdown_document(file_path)
            doc_chunks = generate_document_chunks(meta, body)
            
            doc_count += 1
            total_chunk_count += len(doc_chunks)

            for chunk in doc_chunks:
                active_chunk_ids.add(chunk.chunk_id)
                
                # Enrich chunk metadata with provenance details
                chunk.metadata["processing_version"] = processing_ver
                chunk.metadata["pipeline_version"] = pipeline_ver
                chunk.metadata["ingested_at"] = ingested_time_str
                chunk.metadata["embedding_model"] = provider.model_name

                # Compare checksums
                stored_checksum = existing_checksums.get(chunk.chunk_id)
                if force or stored_checksum != chunk.metadata["checksum"]:
                    chunks_to_embed.append(chunk)

        except Exception as e:
            logger.error("index.parse_failed", f"Failed to parse document {file_path}: {str(e)}")
            raise

    # 4. Generate embeddings and upsert in batches
    vectors_inserted = 0
    if chunks_to_embed:
        logger.info("index.embedding", f"Generating embeddings for {len(chunks_to_embed)} new/changed chunks.", count=len(chunks_to_embed))
        
        for i in range(0, len(chunks_to_embed), batch_size):
            batch = chunks_to_embed[i : i + batch_size]
            batch_contents = [c.content for c in batch]
            batch_ids = [c.chunk_id for c in batch]
            batch_metadatas = [c.metadata for c in batch]

            # Generate vectors via provider
            batch_vectors = await provider.embed_texts(batch_contents)

            # Upsert into semantic store
            await store.upsert_chunks(
                collection_name=collection_name,
                ids=batch_ids,
                vectors=batch_vectors,
                metadatas=batch_metadatas,
                contents=batch_contents,
            )
            vectors_inserted += len(batch)
    else:
        logger.info("index.up_to_date", "All local documents up-to-date. No embeddings required.")

    # 5. Pruning obsolete deleted documents/chunks
    # Any chunk in the collection that is not active in the current run is obsolete
    obsolete_ids = []
    for rec in existing_records:
        cid = rec["id"]
        if cid not in active_chunk_ids:
            obsolete_ids.append(cid)

    if obsolete_ids:
        logger.info("index.pruning", f"Pruning {len(obsolete_ids)} obsolete vector chunks.", count=len(obsolete_ids))
        await store.delete_chunks(collection_name, obsolete_ids)

    logger.info(
        "index.success",
        f"Completed corpus indexing. Docs: {doc_count}, Chunks: {total_chunk_count}, Added: {vectors_inserted}, Pruned: {len(obsolete_ids)}",
        documents=doc_count,
        chunks=total_chunk_count,
    )

    return {
        "documents": doc_count,
        "chunks": total_chunk_count,
        "vectors_inserted": vectors_inserted,
        "pruned": len(obsolete_ids),
    }


async def run_indexing_pipeline(
    config_path: str = "config/corpora.yaml",
    mock_mode: bool = False,
    force: bool = False,
    client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute ingestion pipeline across all configured corpora targets."""
    start_time = time.time()
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # Initialize abstractions
    if mock_mode:
        provider = MockEmbeddingProvider()
    else:
        provider = DashScopeEmbeddingProvider()

    store = ChromaStore(client=client)
    batch_size = config_data.get("pipeline", {}).get("embedding_batch_size", 32)
    corpus_version = config_data.get("version", "1.0.0")

    corpora = config_data.get("corpora", {})
    
    metrics = {
        "document_count": 0,
        "chunk_count": 0,
        "vector_count": 0,
        "pruned_count": 0,
    }

    failures = []
    warnings = []

    # Process each corpus
    for c_name, c_cfg in corpora.items():
        folder_path = c_cfg.get("path")
        collection_name = c_cfg.get("collection")
        try:
            stats = await index_corpus_folder(
                corpus_name=c_name,
                folder_path=folder_path,
                collection_name=collection_name,
                provider=provider,
                store=store,
                batch_size=batch_size,
                force=force,
            )
            metrics["document_count"] += stats["documents"]
            metrics["chunk_count"] += stats["chunks"]
            metrics["vector_count"] += stats["vectors_inserted"]
            metrics["pruned_count"] += stats["pruned"]
        except Exception as e:
            failures.append(f"Corpus {c_name} failed: {str(e)}")

    duration_ms = int((time.time() - start_time) * 1000)

    # Export Manifest
    manifest_dir = "data/corpus/processed/manifests"
    os.makedirs(manifest_dir, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest_path = os.path.join(manifest_dir, f"{timestamp}_manifest.json")

    # Generate aggregate checksum hash
    agg_hash_input = f"{corpus_version}_{metrics['chunk_count']}_{duration_ms}"
    manifest_checksum = hashlib.sha256(agg_hash_input.encode()).hexdigest()

    manifest_data = ManifestModel(
        corpus_version=corpus_version,
        embedding_provider="MockProvider" if mock_mode else "DashScope",
        embedding_model=provider.model_name,
        metrics=ManifestMetrics(
            document_count=metrics["document_count"],
            chunk_count=metrics["chunk_count"],
            vector_count=metrics["vector_count"],
            duration_ms=duration_ms
        ),
        failures=failures,
        warnings=warnings,
        checksum_sha256=manifest_checksum
    )

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data.model_dump(), f, indent=2)

    logger.info("pipeline.completed", f"Ingestion pipeline run finished. Manifest exported to: {manifest_path}")
    
    return {
        "status": "success" if not failures else "partial_failure",
        "metrics": metrics,
        "manifest_path": manifest_path,
        "failures": failures,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridPilot Semantic Ingestion Pipeline CLI")
    parser.add_argument("--config", default="config/corpora.yaml", help="Path to config corpora.yaml")
    parser.add_argument("--mock", action="store_true", help="Run in offline mode using MockEmbeddingProvider")
    parser.add_argument("--force", action="store_true", help="Force re-embedding of all text documents")

    args = parser.parse_args()

    import asyncio
    try:
        asyncio.run(
            run_indexing_pipeline(
                config_path=args.config,
                mock_mode=args.mock,
                force=args.force,
            )
        )
    except Exception as exc:
        sys.stderr.write(f"Pipeline execution crash: {str(exc)}\n")
        sys.exit(1)
