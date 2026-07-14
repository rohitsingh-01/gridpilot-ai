"""Unit and integration tests for the semantic memory indexing pipeline."""
from __future__ import annotations

import json
import os
import shutil
import pytest
import chromadb
from pydantic import ValidationError

from services.semantic.models.schemas import CorpusFrontmatter
from services.semantic.chunking.chunker import parse_markdown_document, generate_document_chunks
from services.semantic.providers.mock import MockEmbeddingProvider
from services.semantic.storage.chroma import ChromaStore
from services.semantic.seed.index_corpus import run_indexing_pipeline

pytestmark = pytest.mark.anyio

TEST_CORPORA_DIR = "test_corpora_lake"
TEST_CONFIG_PATH = "config_test_corpora.yaml"


@pytest.fixture(autouse=True)
def clean_test_environment():
    """Ensure test data directories and test configs are clean before and after tests."""
    for path in [TEST_CORPORA_DIR, TEST_CONFIG_PATH]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    
    os.makedirs(os.path.join(TEST_CORPORA_DIR, "regulatory"), exist_ok=True)
    os.makedirs(os.path.join(TEST_CORPORA_DIR, "environmental"), exist_ok=True)

    yield

    for path in [TEST_CORPORA_DIR, TEST_CONFIG_PATH]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)


def write_test_documents():
    """Create test markdown documents in the test directory."""
    doc_reg = """---
document_id: "test_doc_regulatory"
title: "Test Regulatory Tariffs"
document_type: "regulatory"
jurisdiction: "Federal"
source: "FERC"
version: "1.0.0"
synthetic_flag: true
effective_date: "2026-07-14"
tags: ["test", "interconnection"]
licensing: "Synthetic"
---
# WARNING: SYNTHETIC — for demonstration only

## Section 1. Interconnection Studies
This is the first paragraph describing studies.

This is the second paragraph describing study parameters.
"""
    doc_env = """---
document_id: "test_doc_environmental"
title: "Test Environmental Guidelines"
document_type: "environmental"
jurisdiction: "State"
source: "DEP"
version: "1.0.0"
synthetic_flag: true
effective_date: "2026-07-14"
tags: ["test", "wetlands"]
licensing: "Synthetic"
---
# WARNING: SYNTHETIC — for demonstration only

## Section 1. Wetland Buffer Zones
This is a paragraph describing a 100-foot buffer zone.

This is a paragraph detailing no-disturb zones within 50 feet of a delineated wetland.
"""
    with open(os.path.join(TEST_CORPORA_DIR, "regulatory", "test_reg.md"), "w", encoding="utf-8") as f:
        f.write(doc_reg)
    with open(os.path.join(TEST_CORPORA_DIR, "environmental", "test_env.md"), "w", encoding="utf-8") as f:
        f.write(doc_env)


def write_test_config():
    """Create test corpora.yaml configuration."""
    cfg_data = {
        "version": "1.0.0",
        "corpora": {
            "regulatory": {
                "path": os.path.join(TEST_CORPORA_DIR, "regulatory"),
                "collection": "test_regulatory_corpus"
            },
            "environmental": {
                "path": os.path.join(TEST_CORPORA_DIR, "environmental"),
                "collection": "test_environmental_corpus"
            }
        },
        "pipeline": {
            "embedding_batch_size": 2,
            "default_provider": "mock",
            "default_store": "chroma"
        }
    }
    with open(TEST_CONFIG_PATH, "w", encoding="utf-8") as f:
        import yaml
        yaml.safe_dump(cfg_data, f)


# --- Test Cases ---

def test_frontmatter_validation():
    """Verify that document frontmatter validation correctly catches schema errors."""
    # Frontmatter with invalid document_type (must be regulatory or environmental)
    bad_frontmatter = {
        "document_id": "test_bad",
        "title": "Bad Title",
        "document_type": "invalid_type",
        "jurisdiction": "State",
        "source": "DEP",
        "version": "1.0.0",
        "effective_date": "2026-07-14"
    }
    with pytest.raises(ValidationError):
        CorpusFrontmatter.model_validate(bad_frontmatter)


def test_markdown_chunker_splitting():
    """Verify chunk generation splits on paragraph boundaries and tracks headings."""
    write_test_documents()
    meta, body = parse_markdown_document(
        os.path.join(TEST_CORPORA_DIR, "regulatory", "test_reg.md")
    )
    assert meta.document_id == "test_doc_regulatory"

    # Set characters size small to trigger multiple chunks
    chunks = generate_document_chunks(meta, body, chunk_size_chars=100, overlap_chars=10)
    assert len(chunks) >= 2
    assert chunks[0].metadata["section_heading"] == "Section 1. Interconnection Studies"
    assert "studies" in chunks[0].content


async def test_mock_embedding_provider():
    """Verify that MockEmbeddingProvider generates deterministic vectors of dimension 1536."""
    provider = MockEmbeddingProvider()
    texts = ["hello", "world"]
    vectors = await provider.embed_texts(texts)
    
    assert len(vectors) == 2
    assert len(vectors[0]) == 1536
    # Verify unit norm (L2 norm should equal 1.0)
    norm = sum(x*x for x in vectors[0]) ** 0.5
    assert pytest.approx(norm) == 1.0

    # Verify determinism
    vectors_repeat = await provider.embed_texts(texts)
    assert vectors[0] == vectors_repeat[0]


async def test_indexing_pipeline_and_idempotency():
    """Verify full ingestion runner executes successfully and handles idempotency and pruning."""
    write_test_documents()
    write_test_config()

    # Initialize local Ephemeral Chroma client to run tests completely in-memory
    client = chromadb.EphemeralClient()
    store = ChromaStore(client=client)

    # 1. Run Ingestion Pipeline
    res = await run_indexing_pipeline(
        config_path=TEST_CONFIG_PATH,
        mock_mode=True,
        force=True,
        client=client
    )
    assert res["status"] == "success"
    assert res["metrics"]["document_count"] == 2
    
    # 2. Check if collections exist and contain vectors
    await store.initialize_collection("test_regulatory_corpus")
    records_reg = await store.get_collection_metadata("test_regulatory_corpus")
    assert len(records_reg) > 0

    # Record initial checksums
    initial_checksum = records_reg[0]["metadata"]["checksum"]

    # 3. Rerun pipeline WITHOUT force (idempotency check)
    res_idempotent = await run_indexing_pipeline(
        config_path=TEST_CONFIG_PATH,
        mock_mode=True,
        force=False,
        client=client
    )
    assert res_idempotent["metrics"]["vector_count"] == 0  # 0 inserted because checksums matched!

    # 4. Modify a file and verify update
    with open(os.path.join(TEST_CORPORA_DIR, "regulatory", "test_reg.md"), "a", encoding="utf-8") as f:
        f.write("\nThis is a brand new paragraph which changes the checksum.")

    res_update = await run_indexing_pipeline(
        config_path=TEST_CONFIG_PATH,
        mock_mode=True,
        force=False,
        client=client
    )
    # The updated document should trigger re-embedding of its modified chunk
    assert res_update["metrics"]["vector_count"] > 0


async def test_indexing_pipeline_pruning():
    """Verify that if a local document is deleted, its vectors are pruned from ChromaDB."""
    write_test_documents()
    write_test_config()

    client = chromadb.EphemeralClient()
    store = ChromaStore(client=client)

    # Ingest initially
    await run_indexing_pipeline(TEST_CONFIG_PATH, mock_mode=True, force=True, client=client)

    # Verify it was inserted
    records_initial = await store.get_collection_metadata("test_regulatory_corpus")
    assert len(records_initial) > 0

    # Delete the regulatory markdown file
    reg_file = os.path.join(TEST_CORPORA_DIR, "regulatory", "test_reg.md")
    os.remove(reg_file)

    # Re-run pipeline (should prune regulatory collection vectors for deleted doc)
    res = await run_indexing_pipeline(TEST_CONFIG_PATH, mock_mode=True, force=False, client=client)
    assert res["metrics"]["pruned_count"] > 0

    records_after = await store.get_collection_metadata("test_regulatory_corpus")
    assert len(records_after) == 0


async def test_rag_retrieval_flow():
    """Verify that querying a collection returns the expected nearest neighbor with metadata."""
    write_test_documents()
    write_test_config()

    client = chromadb.EphemeralClient()
    store = ChromaStore(client=client)

    # Index files
    await run_indexing_pipeline(TEST_CONFIG_PATH, mock_mode=True, force=True, client=client)

    # Instantiate query and mock embedding provider
    provider = MockEmbeddingProvider()
    query_text = "buffer zone"
    query_vector = (await provider.embed_texts([query_text]))[0]

    # Query environmental collection (where the buffer zone text is located)
    results = await store.query_semantic(
        collection_name="test_environmental_corpus",
        query_vector=query_vector,
        limit=1
    )

    assert len(results) == 1
    # Verify the matching chunk matches environmental buffer zone content
    assert "100-foot buffer zone" in results[0]["content"]
    # Check that provenance metadata properties are correctly propagated
    assert results[0]["metadata"]["document_id"] == "test_doc_environmental"
    assert results[0]["metadata"]["jurisdiction"] == "State"
    assert results[0]["metadata"]["synthetic_flag"] is True
    assert "ingested_at" in results[0]["metadata"]
