# Official Milestone 14 — Environmental Permit Agent Tasks

## 1. models.py & prompts.py
- [x] Create Pydantic report models, `ReasoningSummary`, and `ConfidenceBreakdown` in `models.py`
- [x] Create placeholders and Qwen template documentations in `prompts.py`

## 2. Reasoning Engine & Report Assembler
- [x] Create isolated pure reasoning functions in `reasoning.py` (confidence, constraints, permit mapping, recommendations)
- [x] Create `report.py` containing `build_report()` supporting SHA-256 generation and validation check

## 3. Core Agent subclass
- [x] Create `agent.py` implementing `EnvironmentalPermitAgent` subclass of `BaseReasoningAgent`
- [x] Support parallel tool runs, cancellations, and telemetry metric logging

## 4. Verification & Testing
- [x] Create `tests/test_environmental_agent.py` verifying executions, fallback scores, hashes, and empty evidence bundles
- [x] Run all tests and verify (100% passing)
