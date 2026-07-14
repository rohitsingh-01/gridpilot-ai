"""Markdown corpus loader, frontmatter validator, and paragraph-preserving semantic chunker."""
from __future__ import annotations

import hashlib
import re
from typing import List, Dict, Any, Tuple
import yaml
from pydantic import BaseModel, ValidationError

from services.semantic.models.schemas import CorpusFrontmatter


class DocumentChunk(BaseModel):
    """Data model representing a generated document chunk with metadata."""
    chunk_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]


def parse_markdown_document(filepath: str) -> Tuple[CorpusFrontmatter, str]:
    """Reads a markdown file, parses and validates its YAML frontmatter, and returns the body."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Match YAML frontmatter between triple dashes at start of file
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        raise ValueError(f"Document missing YAML frontmatter: {filepath}")

    frontmatter_text = match.group(1)
    body_text = content[match.end():]

    try:
        yaml_data = yaml.safe_load(frontmatter_text)
    except Exception as e:
        raise ValueError(f"Invalid YAML syntax in frontmatter of {filepath}: {str(e)}")

    try:
        metadata = CorpusFrontmatter.model_validate(yaml_data)
    except ValidationError as e:
        raise ValueError(f"Frontmatter metadata validation failed for {filepath}: {str(e)}")

    return metadata, body_text


def generate_document_chunks(
    doc_metadata: CorpusFrontmatter,
    body_text: str,
    chunk_size_chars: int = 1500,
    overlap_chars: int = 150,
) -> List[DocumentChunk]:
    """Chunks document body by paragraph, tracking parent headings and generating SHA-256 keys."""
    # Split text into lines to track headings
    lines = body_text.splitlines()
    
    # Pre-parse heading segments and group lines by paragraphs
    paragraphs: List[Tuple[str, str]] = []  # (paragraph_content, last_seen_heading)
    current_heading = "Root"
    current_paragraph_lines = []

    for line in lines:
        stripped = line.strip()
        # Detect markdown heading
        if stripped.startswith("#"):
            # If we have a pending paragraph, flush it
            if current_paragraph_lines:
                p_text = "\n".join(current_paragraph_lines).strip()
                if p_text:
                    paragraphs.append((p_text, current_heading))
                current_paragraph_lines = []
            
            # Extract heading text (strip leading # and spaces)
            current_heading = re.sub(r"^#+\s*", "", stripped)
        else:
            # Accumulate lines
            if stripped == "":
                # Paragraph separator
                if current_paragraph_lines:
                    p_text = "\n".join(current_paragraph_lines).strip()
                    if p_text:
                        paragraphs.append((p_text, current_heading))
                    current_paragraph_lines = []
            else:
                current_paragraph_lines.append(line)

    # Flush final paragraph
    if current_paragraph_lines:
        p_text = "\n".join(current_paragraph_lines).strip()
        if p_text:
            paragraphs.append((p_text, current_heading))

    chunks: List[DocumentChunk] = []
    current_chunk_paragraphs = []
    current_chunk_len = 0
    chunk_index = 0

    for p_text, heading in paragraphs:
        p_len = len(p_text)
        
        # If adding this paragraph exceeds chunk size, flush the current chunk
        if current_chunk_len + p_len > chunk_size_chars and current_chunk_paragraphs:
            # Merge current chunk paragraphs
            chunk_content = "\n\n".join(current_chunk_paragraphs)
            
            # Generate deterministic SHA-256 chunk ID
            chunk_id_input = f"{doc_metadata.document_id}_{chunk_index}"
            chunk_id = hashlib.sha256(chunk_id_input.encode("utf-8")).hexdigest()
            chunk_checksum = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()

            # Compile metadata
            metadata = {
                "document_id": doc_metadata.document_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "document_version": doc_metadata.version,
                "source": doc_metadata.source,
                "jurisdiction": doc_metadata.jurisdiction,
                "section_heading": heading,  # Inherit current paragraph's heading
                "synthetic_flag": doc_metadata.synthetic_flag,
                "checksum": chunk_checksum,
            }

            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    chunk_index=chunk_index,
                    content=chunk_content,
                    metadata=metadata
                )
            )

            # Implement overlap by keeping the last paragraph if small enough, or reset
            if len(current_chunk_paragraphs[-1]) < overlap_chars:
                current_chunk_paragraphs = [current_chunk_paragraphs[-1], p_text]
                current_chunk_len = len(current_chunk_paragraphs[0]) + len(p_text)
            else:
                current_chunk_paragraphs = [p_text]
                current_chunk_len = p_len
            
            chunk_index += 1
        else:
            current_chunk_paragraphs.append(p_text)
            current_chunk_len += p_len + 2  # Add 2 for "\n\n" separator

    # Flush final chunk
    if current_chunk_paragraphs:
        chunk_content = "\n\n".join(current_chunk_paragraphs)
        chunk_id_input = f"{doc_metadata.document_id}_{chunk_index}"
        chunk_id = hashlib.sha256(chunk_id_input.encode("utf-8")).hexdigest()
        chunk_checksum = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
        
        # Last heading context
        last_heading = paragraphs[-1][1] if paragraphs else "Root"

        metadata = {
            "document_id": doc_metadata.document_id,
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "document_version": doc_metadata.version,
            "source": doc_metadata.source,
            "jurisdiction": doc_metadata.jurisdiction,
            "section_heading": last_heading,
            "synthetic_flag": doc_metadata.synthetic_flag,
            "checksum": chunk_checksum,
        }

        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                chunk_index=chunk_index,
                content=chunk_content,
                metadata=metadata
            )
        )

    return chunks
