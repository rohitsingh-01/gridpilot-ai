"""Pydantic validation schemas for document frontmatter metadata and run manifests."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class CorpusFrontmatter(BaseModel):
    """Schema validating the YAML frontmatter header of a corpus markdown file."""
    document_id: str
    title: str
    document_type: str = Field(pattern="^(regulatory|environmental)$")
    jurisdiction: str
    source: str
    version: str
    synthetic_flag: bool = Field(default=True)
    effective_date: str
    tags: List[str] = Field(default_factory=list)
    licensing: str = Field(default="Synthetic Demonstration")


class ManifestMetrics(BaseModel):
    """Ingestion statistics metrics."""
    document_count: int
    chunk_count: int
    vector_count: int
    duration_ms: int
    tokens_consumed: int = Field(default=0)


class ManifestModel(BaseModel):
    """Run summary execution manifest schema."""
    corpus_version: str
    embedding_provider: str
    embedding_model: str
    metrics: ManifestMetrics
    failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checksum_sha256: str
    software_version: str = Field(default="GridPilot SemanticIndexer 1.0.0")
