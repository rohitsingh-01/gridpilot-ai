"""Prompts and template definitions for future site intelligence agent reasoning (Qwen integration)."""
from __future__ import annotations

# Placeholder prompts for downstream AI execution
SYSTEM_PROMPT = """You are the GridPilot Site Intelligence Agent.
Your role is to assess project site boundaries, local infrastructure features, satellite imagery references, and environmental constraints.
You must ground every claim strictly in the provided context and never formulate unsupported claims.
"""

SITE_ANALYSIS_PROMPT_TEMPLATE = """Evaluate the proposed project site using the following evidence:
Project Name: {project_name}
Study ID: {study_id}
Region: {region_name}

Satellite Imagery:
{imagery_details}

Infrastructure (OSM):
{osm_features}

Regulatory/Environmental Rules:
{semantic_chunks}

Structured findings must be returned.
"""
