"""Placeholder configurations for future Qwen LLM integration templates."""
from __future__ import annotations

# System and reasoning templates to instruct Qwen-2.5-72B-Instruct
SYSTEM_PROMPT = """
You are the GridPilot Environmental Permit Agent. Your task is to evaluate environmental constraints (wetlands, habitats, regulatory buffer setbacks) and compile permit filings requirements.
"""

REASONING_TEMPLATE = """
Context: {context}
Evidence: {evidence}
Analyze environmental regulations and list all required agency approvals.
"""

REPORT_TEMPLATE = """
Build the final structured permitting assessment and mitigation recommendations.
"""
