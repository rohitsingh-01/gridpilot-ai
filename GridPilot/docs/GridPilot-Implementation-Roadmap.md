# GridPilot — Implementation Roadmap

**Derived from:** `GridPilot-EDD.md` v1.0
**Purpose:** A sequenced list of 40 milestones for building GridPilot inside **Antigravity**. No code is generated in this document — every milestone is a scoped unit of work you hand to the AI IDE, verify, and commit before moving on.

**The loop, every milestone, no exceptions:**

```
Read milestone card  →  Build in Antigravity  →  Run acceptance test(s)  →  git commit  →  next milestone
```

If a milestone's acceptance criteria don't pass, **do not proceed to the next milestone.** Every later milestone assumes every earlier one is done and working — that assumption is the entire point of breaking a 5-day build into 40 small, independently verifiable steps instead of one large one.

## How to Read Each Card

| Field | Meaning |
|---|---|
| **Phase** | Which EDD Build Phase (1–6) this milestone belongs to |
| **Time** | Realistic solo effort, 30–90 minutes |
| **Inputs** | What must already exist (files, running services, external accounts) before you start |
| **Outputs** | What concretely exists after the milestone that didn't before |
| **Files** | The exact files created or modified (paths match the EDD's Folder Structure section exactly) |
| **Depends on** | Milestone numbers that must be complete and committed first |
| **Acceptance criteria** | The specific, checkable test(s) that prove the milestone is done — this is the "Test" step in the loop |
| **Commit message** | Suggested Conventional Commit message for the "Git Commit" step |

## Milestone Map

| # | Milestone | Phase | Time | Depends on |
|---|---|---|---|---|
| 1 | Repo scaffold + infra Docker Compose skeleton | 1 | 60–90 min | — |
| 2 | Alibaba Cloud provisioning (ECS, OSS, DashScope, RAM) | 1 | 60–90 min | — |
| 3 | Shared Pydantic schema library | 1 | 45–60 min | 1 |
| 4 | SQLAlchemy models + Alembic setup | 1 | 60–90 min | 1, 3 |
| 5 | Apply initial migration | 1 | 30–45 min | 1, 4 |
| 6 | Seed script: grid topology + demo region/project/user | 1 | 75–90 min | 5 |
| 7 | Free geospatial dataset acquisition (NWI + habitat) | 1 | 60–75 min | 6 |
| 8 | Satellite imagery pre-cache pipeline | 1 | 60–90 min | 2, 6 |
| 9 | Write + embed regulatory & environmental corpora | 1 | 75–90 min | 1, 2 |
| 10 | Shared agent infrastructure | 2 | 45–60 min | 2, 3 |
| 11 | Site Intelligence Agent — tools.py | 2 | 60–75 min | 8, 10 |
| 12 | Site Intelligence Agent — agent.py + tests | 2 | 75–90 min | 9, 11 |
| 13 | Environmental Permit Agent — tools.py | 2 | 60–75 min | 7, 10 |
| 14 | Environmental Permit Agent — agent.py + tests | 2 | 75–90 min | 9, 13 |
| 15 | Power Flow Agent — simulation.py | 2 | 75–90 min | 6, 10 |
| 16 | Power Flow Agent — agent.py + tests | 2 | 75–90 min | 15 |
| 17 | Cost Allocation Agent — full module | 2 | 60–90 min | 16 |
| 18 | Regulatory Agent — citation_check.py + schemas | 2 | 45–60 min | 9, 10 |
| 19 | Regulatory Agent — agent.py + tests | 2 | 75–90 min | 12, 14, 16, 17, 18 |
| 20 | Orchestrator — state.py + routing.py | 3 | 60–75 min | 12, 14, 16, 17, 19 |
| 21 | Orchestrator — escalation.py + tests | 3 | 45–60 min | 20 |
| 22 | Orchestrator — graph.py (LangGraph wiring) | 3 | 75–90 min | 21 |
| 23 | Memory services — short_term.py + audit.py | 3 | 60–75 min | 5, 22 |
| 24 | End-to-end integration test | 3 | 60–90 min | 22, 23 |
| 25 | Auth: DB session + dependency + router | 4 | 60–75 min | 5 |
| 26 | Projects router + Grid router | 4 | 60–75 min | 25 |
| 27 | Studies router (create/get/list) | 4 | 75–90 min | 24, 26 |
| 28 | SSE progress stream | 4 | 60–75 min | 27 |
| 29 | Human review endpoints + resume | 4 | 60–75 min | 27 |
| 30 | Document generation (OSS + PDF) | 4 | 75–90 min | 29 |
| 31 | Next.js scaffold + generated API types | 5 | 45–60 min | 30 |
| 32 | Design system primitives | 5 | 45–60 min | 31 |
| 33 | Login screen | 5 | 30–45 min | 25, 32 |
| 34 | Dashboard screen | 5 | 45–60 min | 26, 33 |
| 35 | Study Live Run screen | 5 | 75–90 min | 28, 34 |
| 36 | Study Review screen | 5 | 75–90 min | 30, 35 |
| 37 | Audit Trail screen | 5 | 45–60 min | 36 |
| 38 | Dockerfiles + full docker-compose + nginx | 6 | 60–90 min | 37 |
| 39 | CI/CD workflows | 6 | 60–75 min | 38 |
| 40 | First live deploy + smoke test + rehearsal | 6 | 75–90 min | 2, 39 |

**Total estimated effort:** ~43 hours, matching the EDD's 5-Day Hackathon Plan at roughly 8–9 focused hours/day. Milestones 1–9 correspond to Build Phase 1, 10–19 to Phase 2, 20–24 to Phase 3, 25–30 to Phase 4, 31–37 to Phase 5, 38–40 to Phase 6 — see the EDD's [Build Phases](#) and [5-Day Hackathon Plan](#) sections for how these map onto calendar days.

---

## Phase 1 — Foundations (Milestones 1–9)

### Milestone 1 — Repo scaffold + infra Docker Compose skeleton

- **Time:** 60–90 min
- **Inputs:** Empty repository, Docker + Docker Compose installed locally.
- **Outputs:** Full directory tree exists (empty placeholder files where needed), and Postgres, Redis, and ChromaDB run locally as containers and are reachable — no application code yet.
- **Files:** `README.md`, `Makefile`, `.env.example`, `docker-compose.yml`, `docker-compose.override.yml`, top-level empty directories for `agents/`, `services/`, `shared/`, `data/`, `frontend/`, `infra/`, `.github/workflows/`, `tests/` matching the EDD's Folder Structure section exactly.
- **Depends on:** None — first milestone.
- **Acceptance criteria:**
  - `docker compose up -d postgres redis chromadb` starts all three containers with no errors.
  - `docker compose ps` shows all three as `running`/`healthy`.
  - `psql` (or any Postgres client) can connect to the `postgres` container using the credentials in `.env.example`.
  - `redis-cli ping` against the `redis` container returns `PONG`.
  - A GET request to the ChromaDB container's heartbeat endpoint returns a 200.
  - Full directory tree matches the EDD's Folder Structure listing (spot-check with `find . -maxdepth 3`).
- **Commit message:** `chore: scaffold repo structure and local infra (postgres, redis, chromadb)`

### Milestone 2 — Alibaba Cloud provisioning (ECS, OSS, DashScope, RAM)

- **Time:** 60–90 min
- **Inputs:** An Alibaba Cloud account (new-account free-tier eligible), no code dependency.
- **Outputs:** One ECS instance running (free-tier eligible spec), one OSS bucket created, a DashScope/Model Studio workspace with an API key issued, and one RAM sub-account with a policy scoped to only that OSS bucket and that DashScope workspace — no root-account credentials used anywhere going forward.
- **Files:** `infra/alibaba/deploy.sh` (documents/automates the provisioning steps), `.env.example` updated with the new environment variable names (`OSS_BUCKET_NAME`, `OSS_ACCESS_KEY_ID`, `OSS_ACCESS_KEY_SECRET`, `DASHSCOPE_API_KEY`, `ECS_HOST`).
- **Depends on:** None — can be done in parallel with Milestone 1.
- **Acceptance criteria:**
  - SSH access to the new ECS instance works using the RAM sub-account's credentials (or a dedicated SSH key), not the root account.
  - A test file can be uploaded to and downloaded from the OSS bucket using the RAM sub-account's scoped credentials (via the Alibaba OSS CLI or SDK, not the console).
  - A trivial DashScope API call (e.g., listing available models, or one minimal text-generation call) succeeds using the issued API key.
  - Confirm the RAM policy attached to the sub-account explicitly does **not** grant access to any other OSS bucket or service.
- **Commit message:** `chore: document Alibaba Cloud provisioning (ECS, OSS, DashScope, RAM)`

### Milestone 3 — Shared Pydantic schema library

- **Time:** 45–60 min
- **Inputs:** Milestone 1 (repo scaffold, Python environment/dependency management set up — `pip`/`poetry`/`uv`, FastAPI + Pydantic v2 installed).
- **Outputs:** The cross-cutting typed vocabulary every agent and every API contract will import — `Source`, `Confidence`, `AgentError`, base `AgentInput`/`AgentOutput` shape references (the actual `base_agent.py` classes come in Milestone 10, but the primitive types they build on live here).
- **Files:** `shared/schemas/__init__.py`, `shared/schemas/common.py` (Source, Confidence, AgentError types), `shared/schemas/geo.py` (AOI/GeoJSON validation types).
- **Depends on:** Milestone 1.
- **Acceptance criteria:**
  - Every type in `shared/schemas/` has at least one unit test instantiating it with valid data and rejecting at least one invalid case (e.g., a `Confidence` value outside 0–1 raises a validation error).
  - `pytest shared/ -v` passes.
  - No file in `shared/schemas/` imports from `agents/` or `services/` (one-directional dependency, checked by a quick `grep -r "from agents" shared/` and `grep -r "from services" shared/` returning nothing).
- **Commit message:** `feat: add shared Pydantic schema library`

### Milestone 4 — SQLAlchemy models + Alembic setup

- **Time:** 60–90 min
- **Inputs:** Milestone 1 (Postgres running), Milestone 3 (shared schema conventions to mirror).
- **Outputs:** SQLAlchemy 2.0 async models for every table in the EDD's Database Design section, and Alembic initialized and configured to talk to the local Postgres container — no migration generated yet.
- **Files:** `services/db/models.py`, `services/db/session.py`, `services/db/migrations/env.py`, `services/db/migrations/alembic.ini` (or repo-root `alembic.ini`, per convention).
- **Depends on:** Milestone 1, Milestone 3.
- **Acceptance criteria:**
  - `services/db/models.py` defines all 14 tables from the EDD schema (`users`, `sessions`, `utility_regions`, `grid_nodes`, `grid_edges`, `projects`, `studies`, `agent_runs`, `power_flow_results`, `cost_allocation_results`, `environmental_flags`, `regulatory_citations`, `human_reviews`, `audit_log`, `documents`) with matching column names, types, and constraints.
  - `alembic revision --autogenerate` runs without errors and without manual intervention needed to fix the generated diff.
  - Every foreign key and every `CHECK` constraint from the EDD schema is present in the generated migration (spot-check the migration file against the EDD's SQL).
- **Commit message:** `feat: add SQLAlchemy models and Alembic configuration`

### Milestone 5 — Apply initial migration

- **Time:** 30–45 min
- **Inputs:** Milestone 1 (Postgres running), Milestone 4 (models + Alembic configured).
- **Outputs:** The full schema is live in the running Postgres database.
- **Files:** `services/db/migrations/versions/0001_initial_schema.py` (or equivalent auto-named file).
- **Depends on:** Milestone 1, Milestone 4.
- **Acceptance criteria:**
  - `alembic upgrade head` completes with no errors against the local `postgres` container.
  - `\dt gridpilot.*` in `psql` lists all 14 expected tables.
  - `\d gridpilot.audit_log` confirms the app DB role has only `INSERT`/`SELECT` grants, not `UPDATE`/`DELETE` (verify by attempting an `UPDATE` as the app role and confirming it is rejected).
  - `alembic downgrade base` followed by `alembic upgrade head` round-trips cleanly (proves the migration is reversible and repeatable).
- **Commit message:** `feat: apply initial database schema migration`

### Milestone 6 — Seed script: grid topology + demo region/project/user

- **Time:** 75–90 min
- **Inputs:** Milestone 5 (schema live).
- **Outputs:** One `utility_regions` row, an 8–15 node synthetic grid topology (`grid_nodes`/`grid_edges`) loosely georeferenced to a real-world AOI chosen for realistic satellite imagery later, one demo `projects` row ("Sagebrush Solar + Storage"), and one seeded engineer `users` row (Priya) with a working password hash.
- **Files:** `data/seed/seed_grid_topology.py`, `data/seed/seed_demo_project.py`, `Makefile` updated with a `make seed` target running both.
- **Depends on:** Milestone 5.
- **Acceptance criteria:**
  - `make seed` runs both scripts against the local database with no errors.
  - Querying `grid_nodes` returns between 8 and 15 rows, all with valid latitude/longitude within the chosen AOI's bounding box.
  - Querying `grid_edges` confirms the network is fully connected (no orphan node unreachable from any other node — verify with a quick NetworkX connectivity check in the script itself or a throwaway script).
  - Exactly one row exists in `projects`, referencing a valid `poi_node_id` from the seeded `grid_nodes`.
  - The seeded user can be looked up by email and its password hash verifies against the known demo password using the hashing library chosen in Milestone 25.
  - Re-running `make seed` is idempotent (does not create duplicate rows) or fails loudly rather than silently duplicating — decide and document which, then verify it.
- **Commit message:** `feat: seed synthetic grid topology, demo project, and demo user`

### Milestone 7 — Free geospatial dataset acquisition (NWI + habitat)

- **Time:** 60–75 min
- **Inputs:** Milestone 6 (the demo AOI/region is now fixed, so the correct geographic extent to download is known).
- **Outputs:** A clipped National Wetlands Inventory GeoJSON extract and a clipped USFWS critical habitat GeoJSON extract, both scoped tightly to the demo region's bounding box and committed to the repo as small files.
- **Files:** `data/raw/` (gitignored, holds the full downloaded source files), `data/processed/nwi_extract.geojson`, `data/processed/habitat_extract.geojson`, a short `data/seed/prepare_environmental_datasets.py` script documenting the clip/convert steps.
- **Depends on:** Milestone 6.
- **Acceptance criteria:**
  - Both output GeoJSON files are valid (parse successfully with any GeoJSON validator or `shapely`/`geopandas` load).
  - Both files are small enough to commit directly to git (target: well under 5MB combined) — confirmed by `git add` and checking the diff size before committing.
  - At least one feature in each file intersects or is near the demo AOI (sanity-checked by loading both files and the AOI polygon together and confirming a non-empty spatial relationship, or explicitly confirming zero intersection if the chosen AOI is genuinely clear — either is a valid, useful outcome for the demo).
  - Every feature retains its original source attribution field so the Environmental Permit Agent can cite `source_dataset` accurately later.
- **Commit message:** `feat: add clipped NWI and USFWS habitat dataset extracts`

### Milestone 8 — Satellite imagery pre-cache pipeline

- **Time:** 60–90 min
- **Inputs:** Milestone 2 (OSS bucket + credentials available), Milestone 6 (demo AOI fixed).
- **Outputs:** A least-cloudy recent Sentinel-2 true-color scene for the demo AOI, clipped, converted to a web-friendly PNG plus a clipped COG, uploaded to OSS — this is the exact artifact the Site Intelligence Agent will read at runtime, produced entirely offline so the live demo has zero dependency on the satellite data API being up.
- **Files:** `data/seed/fetch_satellite_tiles.py`.
- **Depends on:** Milestone 2, Milestone 6.
- **Acceptance criteria:**
  - Running the script once produces a PNG and a COG file, both visually confirmed (open the PNG) to show real, recognizable imagery of the demo AOI, not a blank/error tile.
  - Both files are successfully uploaded to the OSS bucket at the documented key pattern (`oss://<bucket>/satellite/{region_id}/{scene_date}.png` and `.tif`).
  - The script records the resulting OSS key back into a place the seed data can reference (e.g., updates the `utility_regions` row or writes a small config file consumed later).
  - Deleting the local output files and re-running the script reproduces an equivalent result without requiring any manual step, proving the pipeline is not dependent on undocumented local state.
- **Commit message:** `feat: add offline satellite imagery pre-cache pipeline`

### Milestone 9 — Write + embed regulatory and environmental corpora

- **Time:** 75–90 min
- **Inputs:** Milestone 1 (repo scaffold), Milestone 2 (DashScope embedding API access).
- **Outputs:** Hand-written, clearly-labeled-as-synthetic regulatory/tariff text and environmental-precedent text, chunked and embedded into two ChromaDB collections (`regulatory_corpus`, `environmental_corpus`).
- **Files:** `data/corpus/regulatory/*.md` (simplified FERC Order 2023 cluster-study concepts + one synthetic state PUC tariff excerpt), `data/corpus/environmental/*.md` (synthetic environmental-filing precedent text), `data/seed/embed_regulatory_corpus.py`, `data/seed/embed_environmental_corpus.py`.
- **Depends on:** Milestone 1, Milestone 2.
- **Acceptance criteria:**
  - Both markdown source directories contain enough content to produce at least 15–20 distinct 500-token chunks per collection (enough for the retrieval agents to have real, varied results to retrieve, not a trivial one-chunk corpus).
  - Every markdown source file has a clear, visible "SYNTHETIC — for demonstration only" header, matching the EDD's data-provenance labeling requirement.
  - Running both embedding scripts populates the `regulatory_corpus` and `environmental_corpus` ChromaDB collections; a test query against each (e.g., "wetland buffer distance requirements") returns non-empty, plausibly relevant results with populated metadata fields (`source_document`, `section`/`flag_type`).
  - Re-running the embedding scripts does not duplicate chunks (either idempotent upsert by a stable chunk ID, or the script clears the collection first — document which).
- **Commit message:** `feat: seed and embed synthetic regulatory and environmental corpora`

---

## Phase 2 — Agents in Isolation (Milestones 10–19)

*Every agent milestone in this phase is tested with a mocked DashScope client — no live Qwen calls, no token spend, no network dependency in these tests. Live-call verification happens once, deliberately, in Milestone 24.*

### Milestone 10 — Shared agent infrastructure

- **Time:** 45–60 min
- **Inputs:** Milestone 2 (DashScope API key available), Milestone 3 (shared schemas).
- **Outputs:** The base classes and thin client every agent builds on: `AgentInput`/`AgentOutput` base Pydantic classes, shared confidence-scoring helpers, and a DashScope client wrapper with an explicit mock mode for tests.
- **Files:** `agents/shared/base_agent.py`, `agents/shared/confidence.py`, `agents/shared/qwen_client.py`, `agents/shared/tests/test_qwen_client.py`.
- **Depends on:** Milestone 2, Milestone 3.
- **Acceptance criteria:**
  - `AgentOutput` (or its subclasses) enforces the presence of `confidence`, `sources`, `assumptions`, and `raw_model_output` fields at the type level — instantiating without them fails validation.
  - The DashScope client wrapper exposes a `mock_mode` (or equivalent) that returns deterministic fixture responses without any network call, verified by a test that asserts zero HTTP calls are made when mocked (e.g., via `responses`/`respx` asserting no unmocked call was attempted).
  - One live smoke test (marked/skippable, not run in normal CI) confirms the wrapper can make one real, minimal DashScope call successfully.
  - `pytest agents/shared/ -v` passes.
- **Commit message:** `feat: add shared agent base classes and DashScope client wrapper`

### Milestone 11 — Site Intelligence Agent: tools.py

- **Time:** 60–75 min
- **Inputs:** Milestone 8 (satellite tile in OSS), Milestone 10 (shared tool-wrapper pattern).
- **Outputs:** Two working, independently-callable tool functions: fetching the pre-cached satellite tile from OSS, and querying OpenStreetMap via Overpass for transmission lines/substations/land-use within a bounding box, with a 24-hour Redis cache in front of the Overpass call.
- **Files:** `agents/site_intelligence/tools.py`, `agents/site_intelligence/tests/test_tools.py`.
- **Depends on:** Milestone 8, Milestone 10.
- **Acceptance criteria:**
  - `fetch_satellite_tile(aoi_bbox)` called with the demo AOI's bounding box returns the actual pre-cached image bytes/reference from OSS, verified against the file uploaded in Milestone 8.
  - `query_osm_features(bbox, tags)` called against the demo AOI's bounding box returns at least one real OSM feature (or explicitly and correctly returns an empty result if none exist — verify manually which is true for the chosen AOI first).
  - Calling `query_osm_features` twice in a row with identical arguments hits the Redis cache on the second call (verified by asserting only one outbound HTTP call was made across both invocations).
  - Every call, cached or not, produces an audit-log-shaped record per the tool-wrapper pattern (full audit *writing* is wired in Milestone 23; this milestone just confirms the record is generated in the correct shape).
- **Commit message:** `feat: add Site Intelligence Agent tools (satellite fetch, OSM query)`

### Milestone 12 — Site Intelligence Agent: agent.py + tests

- **Time:** 75–90 min
- **Inputs:** Milestone 9 (semantic memory corpora available for precedent retrieval), Milestone 11 (tools working).
- **Outputs:** The complete Site Intelligence Agent — a `run(state) -> SiteReport` function that calls the vision-capable Qwen model with the satellite tile and OSM data, and falls back gracefully to OSM-only reasoning with a capped confidence if the imagery is unavailable.
- **Files:** `agents/site_intelligence/agent.py`, `agents/site_intelligence/prompts/analyze_site.md`, `agents/site_intelligence/schemas.py` (`SiteReport`), `agents/site_intelligence/tests/test_agent.py`.
- **Depends on:** Milestone 9, Milestone 11.
- **Acceptance criteria:**
  - Calling `run()` with a fixture `state` (mocked Qwen client, mocked tool responses) returns a valid `SiteReport` with all required fields populated, including a `confidence` between 0 and 1.
  - A fixture test simulating a missing/corrupt OSS imagery key produces a `SiteReport` with `confidence <= 0.6` and a non-empty `assumptions` list explicitly noting the fallback — proving the failure-case behavior described in the EDD, not just the happy path.
  - `pytest agents/site_intelligence/ -v` passes with zero live network or DashScope calls.
  - The agent can be run standalone (`python -m agents.site_intelligence.agent` or equivalent) against the real seeded demo project with mock Qwen responses and produces a plausible, readable `SiteReport`.
- **Commit message:** `feat: implement Site Intelligence Agent`

### Milestone 13 — Environmental Permit Agent: tools.py

- **Time:** 60–75 min
- **Inputs:** Milestone 7 (NWI + habitat extracts available), Milestone 10.
- **Outputs:** Two geometry-intersection tool functions against the clipped NWI and habitat datasets.
- **Files:** `agents/environmental_permit/tools.py`, `agents/environmental_permit/tests/test_tools.py`.
- **Depends on:** Milestone 7, Milestone 10.
- **Acceptance criteria:**
  - `intersect_wetlands(aoi_geojson)` and `intersect_habitat(aoi_geojson)` both return correctly-typed results (empty list vs. list of conflicts) against the real demo project's AOI.
  - A fixture test passing a deliberately malformed/self-intersecting polygon triggers the tool's error path rather than crashing or silently returning "no conflict" — this directly tests the fail-closed requirement from the EDD.
  - A fixture test with a synthetic polygon known to overlap a feature in the test data confirms the tool correctly reports a conflict with accurate `distance_m` (0, since it overlaps) and correct `source_dataset` attribution.
- **Commit message:** `feat: add Environmental Permit Agent geometry-intersection tools`

### Milestone 14 — Environmental Permit Agent: agent.py + tests

- **Time:** 75–90 min
- **Inputs:** Milestone 9 (environmental corpus embedded), Milestone 13 (tools working).
- **Outputs:** The complete Environmental Permit Agent, including the explicit fail-closed behavior on geometry errors (returns `review_required: true`, `confidence: 0.0`, hard escalation — never silently passes).
- **Files:** `agents/environmental_permit/agent.py`, `agents/environmental_permit/prompts/summarize_conflicts.md`, `agents/environmental_permit/schemas.py` (`EnvReport`), `agents/environmental_permit/tests/test_agent.py`.
- **Depends on:** Milestone 9, Milestone 13.
- **Acceptance criteria:**
  - Happy-path fixture test (no conflicts) returns an `EnvReport` with `review_required: false` and a plausible plain-language summary grounded in retrieved corpus chunks.
  - Conflict fixture test (AOI overlapping a seeded wetland/habitat feature) returns `review_required: true` with the specific conflicting feature described.
  - Geometry-error fixture test confirms `review_required: true`, `confidence: 0.0`, and **no retry is attempted** (retry strategy is explicitly "none" for this failure case per the EDD — assert the mocked tool was called exactly once).
  - `pytest agents/environmental_permit/ -v` passes.
- **Commit message:** `feat: implement Environmental Permit Agent with fail-closed geometry handling`

### Milestone 15 — Power Flow Agent: simulation.py

- **Time:** 75–90 min
- **Inputs:** Milestone 6 (grid topology seeded), Milestone 10.
- **Outputs:** The pure-computation core — no LLM involved — that builds a PyPSA network from the seeded NetworkX-shaped topology, injects the project as a generator at its POI bus, and runs a configurable-size Monte Carlo ensemble of DC power-flow scenarios, tallying thermal and voltage violations and non-convergent scenarios.
- **Files:** `agents/power_flow/simulation.py`, `agents/power_flow/tests/test_simulation.py`.
- **Depends on:** Milestone 6, Milestone 10.
- **Acceptance criteria:**
  - Running the simulation against the real seeded demo topology with a small scenario count (e.g., 20, for test speed) completes without unhandled exceptions and returns a `violation_probability` between 0 and 1.
  - A fixture test with a deliberately oversized injected project (e.g., 10x the network's total thermal capacity) reliably produces a high `violation_probability`, proving the physics logic actually responds to load, not just returning a constant.
  - A fixture test that forces some scenarios to fail to converge confirms those scenarios are excluded from the ensemble and correctly reduce `confidence` rather than being silently treated as "no violation" — this is the specific failure-case behavior called out in the EDD.
  - Doubling the scenario count on an otherwise-identical run changes `confidence` (proving the retry mechanism this feeds into Milestone 16 will actually have an effect) without changing the underlying network definition.
- **Commit message:** `feat: implement Power Flow Agent DC power-flow Monte Carlo simulation core`

### Milestone 16 — Power Flow Agent: agent.py + tests

- **Time:** 75–90 min
- **Inputs:** Milestone 15 (simulation core working).
- **Outputs:** The agent wrapper around the simulation core — calls `simulation.py`, then uses a text-only Qwen call to narrate the numeric result into a plain-language summary for later inclusion in the study document.
- **Files:** `agents/power_flow/agent.py`, `agents/power_flow/prompts/summarize_results.md`, `agents/power_flow/schemas.py` (`PowerFlowReport`), `agents/power_flow/tests/test_agent.py`.
- **Depends on:** Milestone 15.
- **Acceptance criteria:**
  - `run()` against the real seeded topology (mocked Qwen narration call) returns a fully-populated `PowerFlowReport` including `scenarios_run`, `violation_probability`, `worst_case_line_loading_pct`, `worst_case_bus_voltage_pu`, and `confidence`.
  - The plain-language narrative in the output is grounded in the actual numeric result (a fixture test can assert the narration prompt received the correct numbers as input — full "the retry actually doubles scenarios" behavior is tested at the orchestrator level in Milestone 21, but this milestone confirms the agent correctly accepts a `scenarios` parameter and passes it through to the simulation core).
  - `pytest agents/power_flow/ -v` passes.
- **Commit message:** `feat: implement Power Flow Agent narration and reporting`

### Milestone 17 — Cost Allocation Agent: full module

- **Time:** 60–90 min
- **Inputs:** Milestone 16 (a real `PowerFlowReport` shape to consume).
- **Outputs:** The complete Cost Allocation Agent in one pass — deterministic unit-cost lookup against a seeded cost table, arithmetic rollup, and an LLM call only for the human-readable cost narrative.
- **Files:** `agents/cost_allocation/unit_costs.py` (seeded `$/MVA` and `$/mile` figures, explicitly labeled illustrative), `agents/cost_allocation/agent.py`, `agents/cost_allocation/prompts/narrate_costs.md`, `agents/cost_allocation/schemas.py` (`CostReport`), `agents/cost_allocation/tests/test_agent.py`.
- **Depends on:** Milestone 16.
- **Acceptance criteria:**
  - `run()` given a fixture `PowerFlowReport` with a known violated line/transformer produces a `CostReport` whose `total_estimated_cost_usd` is arithmetically correct given the seeded unit-cost table (assert the exact number, not just "non-zero").
  - A fixture test with an upgrade type missing from the unit-cost table produces a `CostReport` with that line item explicitly flagged (`cost_estimated: false`) rather than omitted — confirms the EDD's specified failure behavior.
  - `pytest agents/cost_allocation/ -v` passes.
- **Commit message:** `feat: implement Cost Allocation Agent`

### Milestone 18 — Regulatory Agent: citation_check.py + schemas

- **Time:** 45–60 min
- **Inputs:** Milestone 9 (regulatory corpus embedded), Milestone 10.
- **Outputs:** The citation-existence check in isolation — the single piece of genuinely novel logic the EDD's own self-review flags as the highest-risk component — built and adversarially tested before it's wired into the full drafting agent.
- **Files:** `agents/regulatory/citation_check.py`, `agents/regulatory/schemas.py` (`StudyDocument`, `Section`, `Citation`), `agents/regulatory/tests/test_citation_check.py`.
- **Depends on:** Milestone 9, Milestone 10.
- **Acceptance criteria:**
  - Given a set of retrieved chunk IDs and a model output whose citations are a subset of those IDs, the check passes.
  - Given a model output containing even one citation ID **not** in the retrieved set, the check fails and flags the specific offending citation.
  - Adversarial test: given zero retrieved chunks (no relevant match found) and a model output that nonetheless contains a fabricated citation, the check correctly fails closed — this is the exact scenario the EDD's Judge Self-Review calls out as the highest-priority thing to verify before it ever appears live.
  - `pytest agents/regulatory/tests/test_citation_check.py -v` passes, including all three cases above as separate test functions.
- **Commit message:** `feat: implement Regulatory Agent citation-existence check`

### Milestone 19 — Regulatory Agent: agent.py + tests

- **Time:** 75–90 min
- **Inputs:** Milestones 12, 14, 16, 17 (the four upstream reports this agent synthesizes), Milestone 18 (citation check).
- **Outputs:** The complete Regulatory Agent — drafts each section of the study document by retrieving corpus chunks and generating grounded prose, running every section through the citation-existence check, with one automatic retry on failure and an explicit "unverified" flag if the retry also fails.
- **Files:** `agents/regulatory/agent.py`, `agents/regulatory/prompts/draft_site_section.md`, `agents/regulatory/prompts/draft_power_flow_section.md`, `agents/regulatory/prompts/draft_cost_section.md`, `agents/regulatory/prompts/draft_environmental_section.md`, `agents/regulatory/tests/test_agent.py`.
- **Depends on:** Milestone 12, Milestone 14, Milestone 16, Milestone 17, Milestone 18.
- **Acceptance criteria:**
  - `run()` given fixture `SiteReport`, `EnvReport`, `PowerFlowReport`, and `CostReport` inputs (mocked Qwen, mocked retrieval) returns a `StudyDocument` with one `Section` per upstream report and at least one `Citation` per section that references a real retrieved chunk.
  - A fixture test where retrieval returns zero relevant chunks for one section confirms that section's text explicitly states no applicable provision was found, rather than fabricating a citation.
  - A fixture test where the mocked model's first output fails the citation check, but its second (retried) output passes, confirms exactly one retry occurs and the final output is clean.
  - A fixture test where **both** attempts fail the citation check confirms the section ships flagged `unverified — engineer must confirm citation` rather than blocking the whole document.
  - `pytest agents/regulatory/ -v` passes.
- **Commit message:** `feat: implement Regulatory Agent with grounded drafting and citation verification`

---

## Phase 3 — Orchestration (Milestones 20–24)

### Milestone 20 — Orchestrator: state.py + routing.py

- **Time:** 60–75 min
- **Inputs:** Milestones 12, 14, 16, 17, 19 (all five agents complete and independently working).
- **Outputs:** The `StudyState` Pydantic model (the single object every agent reads from and writes to) and the conditional routing functions that decide, after each node, whether to continue, retry, or escalate — implemented and unit-tested as pure functions, before any LangGraph wiring exists.
- **Files:** `agents/orchestrator/state.py`, `agents/orchestrator/routing.py`, `agents/orchestrator/tests/test_routing.py`.
- **Depends on:** Milestone 12, Milestone 14, Milestone 16, Milestone 17, Milestone 19.
- **Acceptance criteria:**
  - `StudyState` can hold a full set of populated agent reports and serializes/deserializes cleanly to/from JSON (proves it's checkpoint-safe ahead of Milestone 22).
  - A routing test asserts: `PowerFlowReport.confidence = 0.61` → routing function returns "retry" (with `retries < 2`); `confidence = 0.61` and `retries = 2` → routing function returns "continue anyway" with the low-confidence result clearly marked; `confidence = 0.82` → routing function returns "continue."
  - `pytest agents/orchestrator/tests/test_routing.py -v` passes for all threshold boundary cases (test exactly at 0.70, just above, just below).
- **Commit message:** `feat: add orchestrator StudyState model and confidence-threshold routing`

### Milestone 21 — Orchestrator: escalation.py + tests

- **Time:** 45–60 min
- **Inputs:** Milestone 20.
- **Outputs:** The deterministic, rule-based (never model-based) conflict resolution logic — "most-conservative-wins" — for cases where two agents disagree (e.g., Site Intelligence says clear, Environmental Permit says review required).
- **Files:** `agents/orchestrator/escalation.py`, `agents/orchestrator/tests/test_escalation.py`.
- **Depends on:** Milestone 20.
- **Acceptance criteria:**
  - A fixture test with `SiteReport.visual_flags = []` and `EnvReport.review_required = true` confirms the resolved outcome forces human escalation regardless of Site Intelligence's confidence — proving "most conservative wins," not an average or a vote.
  - A fixture test confirms this function makes **zero** calls to the Qwen client (assert the mocked client's call count is 0) — this is a deliberately non-LLM code path per the EDD, and the test exists specifically to guarantee it stays that way.
  - `pytest agents/orchestrator/tests/test_escalation.py -v` passes.
- **Commit message:** `feat: add deterministic conflict-resolution escalation logic`

### Milestone 22 — Orchestrator: graph.py (LangGraph wiring)

- **Time:** 75–90 min
- **Inputs:** Milestone 21 (all orchestrator logic pieces working individually).
- **Outputs:** The actual executable LangGraph `StateGraph` wiring all five agents together per the EDD's Workflow State Machine diagram, with Postgres checkpointing after every node transition.
- **Files:** `agents/orchestrator/graph.py`, `agents/orchestrator/tests/test_graph.py`.
- **Depends on:** Milestone 21.
- **Acceptance criteria:**
  - Invoking the compiled graph against the real seeded demo project (all Qwen calls mocked) walks through every node in the exact order shown in the EDD's `stateDiagram-v2`: `Submitted → SiteAnalysis → EnvironmentalReview → PowerFlowSimulation → [retry loop if applicable] → CostAllocation → RegulatoryDrafting → PendingHumanReview`.
  - A test that mocks the Power Flow Agent to return `confidence = 0.61` on its first call and `confidence = 0.82` on its second confirms the graph actually loops back through `PowerFlowRetry` exactly once before proceeding — this is the single most important behavior in the entire product and deserves its own explicit, named test.
  - After each node, a checkpoint row is visible in `studies.state_snapshot` with the correct partial state (verified by querying Postgres directly mid-test, or after each step if the test harness allows step-by-step invocation).
  - `pytest agents/orchestrator/tests/test_graph.py -v` passes.
- **Commit message:** `feat: wire orchestrator LangGraph StateGraph with Postgres checkpointing`

### Milestone 23 — Memory services: short_term.py + audit.py

- **Time:** 60–75 min
- **Inputs:** Milestone 5 (schema live, `audit_log` role permissions applied), Milestone 22 (graph exists to emit events from).
- **Outputs:** The dedicated memory-layer modules: `short_term.py` (reads/writes the `StudyState` checkpoint to `studies.state_snapshot`) and `audit.py` (the single, sole writer to the append-only `audit_log` table), wired into the orchestrator so every node transition and tool/model call is actually logged, not just theoretically loggable.
- **Files:** `services/memory/short_term.py`, `services/memory/audit.py`, `services/memory/tests/test_short_term.py`, `services/memory/tests/test_audit.py`.
- **Depends on:** Milestone 5, Milestone 22.
- **Acceptance criteria:**
  - Running the orchestrator graph against the seeded demo project (mocked Qwen) produces a full, ordered sequence of `audit_log` rows: one `state_transition` per node, one `tool_call` per tool invocation, one `model_call` per Qwen call — verified by querying `audit_log WHERE study_id = ...` after the run and checking the `action` column distribution matches expectations.
  - Attempting to `UPDATE` or `DELETE` an existing `audit_log` row using the app's DB role fails (re-confirms Milestone 5's role permissions are actually enforced from application code, not just from `psql`).
  - Killing the process mid-run (simulated by raising an exception after a partial number of nodes complete) and then resuming via `short_term.py`'s checkpoint-read function confirms the graph resumes from the last completed node, not from the beginning.
  - `pytest services/memory/ -v` passes.
- **Commit message:** `feat: implement audit-log and checkpoint memory services, wire into orchestrator`

### Milestone 24 — End-to-end integration test

- **Time:** 60–90 min
- **Inputs:** Milestone 22, Milestone 23 (full orchestration + memory working with mocks).
- **Outputs:** The one integration test in the whole project that makes **real** DashScope calls end-to-end — the first genuine confirmation that the system works against the actual Qwen API, not just against mocks, including a logged token-cost tally for the run.
- **Files:** `tests/integration/test_full_study_run.py`.
- **Depends on:** Milestone 22, Milestone 23.
- **Acceptance criteria:**
  - Submitting the real seeded demo project through the real graph, with real DashScope calls (no mocking), reaches `PendingHumanReview` status with all five agent reports populated.
  - The test asserts `overall_confidence` is present and prints (or logs) the total `qwen_input_tokens`/`qwen_output_tokens` consumed across the run, confirming it falls within the EDD's expected 10–15 calls / low-cost estimate.
  - The test is explicitly marked (e.g., `@pytest.mark.live`) and excluded from the default CI run configured in Milestone 39, since it costs real (if tiny) money and depends on network access — document this exclusion in the test file itself.
  - Run this test at least twice in a row and confirm the confidence-retry path (Power Flow Agent) fires naturally at least once across the two runs, given real model variance — if it never fires naturally, note this and consider tuning the Monte Carlo scenario count/threshold before Phase 4, since the live demo depends on this being a real, observable behavior.
- **Commit message:** `test: add end-to-end integration test with live DashScope calls`

---

## Phase 4 — API + SSE (Milestones 25–30)

### Milestone 25 — Auth: DB session + dependency + router

- **Time:** 60–75 min
- **Inputs:** Milestone 5 (schema live, `users`/`sessions` tables exist).
- **Outputs:** The FastAPI app's async DB session management, the single `get_current_user` dependency used by every protected route, and the login/logout endpoints with hashed-token, `HttpOnly` cookie-based sessions.
- **Files:** `services/api/main.py` (initial FastAPI app instance), `services/db/session.py`, `services/api/dependencies.py`, `services/api/routers/auth.py`, `services/api/routers/health.py`, `services/api/tests/test_auth.py`.
- **Depends on:** Milestone 5.
- **Acceptance criteria:**
  - `GET /api/v1/health` returns 200 with individual `db`/`chroma`/`dashscope` status fields, each independently checked (verified by temporarily pointing one dependency at a bad connection string and confirming only that field reports failure).
  - `POST /api/v1/auth/login` with the seeded Priya credentials returns a session cookie and a 200; with wrong credentials returns 401.
  - A protected test route decorated with `get_current_user` returns 401 with no cookie, and 200 with a valid session cookie.
  - Inspecting the `sessions` table confirms the stored `token_hash` is not the raw cookie value (hashed, per the EDD's security requirement).
  - `pytest services/api/tests/test_auth.py -v` passes.
- **Commit message:** `feat: implement authentication endpoints and session-based auth dependency`

### Milestone 26 — Projects router + Grid router

- **Time:** 60–75 min
- **Inputs:** Milestone 25 (auth dependency to protect these routes).
- **Outputs:** `POST/GET /api/v1/projects`, `GET /api/v1/projects/{id}`, and `GET /api/v1/grid/{region_id}/topology` fully working against the real seeded data.
- **Files:** `services/api/routers/projects.py`, `services/api/routers/grid.py`, `services/api/tests/test_projects.py`, `services/api/tests/test_grid.py`.
- **Depends on:** Milestone 25.
- **Acceptance criteria:**
  - `GET /api/v1/projects` (authenticated) returns the one seeded demo project with `total: 1`.
  - `POST /api/v1/projects` with a valid new project body creates a row and returns 201; with an invalid body (e.g., `capacity_mw: -5`) returns a 422 validation error, not a 500.
  - `GET /api/v1/grid/{region_id}/topology` returns valid GeoJSON containing all seeded nodes and edges (feature count matches the database row count exactly).
  - All routes reject unauthenticated requests with 401.
  - `pytest services/api/tests/test_projects.py services/api/tests/test_grid.py -v` passes.
- **Commit message:** `feat: implement projects and grid topology API routers`

### Milestone 27 — Studies router (create/get/list)

- **Time:** 75–90 min
- **Inputs:** Milestone 24 (a working, callable `orchestrator.run_study(study_id)` function), Milestone 26.
- **Outputs:** `POST /api/v1/projects/{id}/studies` (kicks off a background study run) and `GET /api/v1/studies/{id}` (returns current status + per-agent progress).
- **Files:** `services/api/routers/studies.py`, `services/api/tests/test_studies.py`.
- **Depends on:** Milestone 24, Milestone 26.
- **Acceptance criteria:**
  - `POST /api/v1/projects/{id}/studies` returns 202 immediately (within a second or two, not waiting for the full study to complete) with a `study_id` and `status: "running"`.
  - Polling `GET /api/v1/studies/{id}` repeatedly over the following minute shows `agent_runs` populating incrementally and `status` eventually reaching `pending_review` — using mocked Qwen calls for test speed, with one manual live-mode run to sanity-check real timing.
  - Calling `POST .../studies` a second time while the first is still `running` either queues correctly or returns a clear conflict response — decide and document the behavior, then test it explicitly (the EDD assumes one study at a time; this test exists precisely to make that assumption an enforced, verified behavior rather than an accident).
  - `pytest services/api/tests/test_studies.py -v` passes.
- **Commit message:** `feat: implement studies API router with background orchestration`

### Milestone 28 — SSE progress stream

- **Time:** 60–75 min
- **Inputs:** Milestone 27 (a running study to stream progress from).
- **Outputs:** `GET /api/v1/studies/{id}/events`, a real Server-Sent Events endpoint forwarding orchestrator node-transition events live, with a terminal `done` event.
- **Files:** `services/api/sse.py`, `services/api/tests/test_sse.py`.
- **Depends on:** Milestone 27.
- **Acceptance criteria:**
  - Opening an SSE connection to a study that's actively running (mocked Qwen, artificially slowed for test observability) yields a sequence of `agent_update` events matching the actual node transitions happening server-side, in the correct order.
  - The stream closes with a final `event: done` carrying the terminal `status`, and the client-side connection can detect stream closure cleanly.
  - Opening an SSE connection to a study that has **already completed** (not currently running) either replays the final state immediately or returns a clear "already complete" signal rather than hanging open indefinitely — decide and test this edge case explicitly.
  - `pytest services/api/tests/test_sse.py -v` passes.
- **Commit message:** `feat: implement SSE study progress stream`

### Milestone 29 — Human review endpoints + resume

- **Time:** 60–75 min
- **Inputs:** Milestone 27 (a study that reaches `pending_review`).
- **Outputs:** `POST /api/v1/studies/{id}/approve`, `/reject`, `/request-changes`, and `POST /api/v1/studies/{id}/resume`, all writing to `human_reviews` and, for approve/reject, updating `studies.status`.
- **Files:** `services/api/routers/studies.py` (extended), `services/api/tests/test_human_review.py`.
- **Depends on:** Milestone 27.
- **Acceptance criteria:**
  - `POST .../approve` on a `pending_review` study writes a `human_reviews` row with `decision: "approved"`, updates `studies.status` to `approved`, and returns 200.
  - `POST .../request-changes` with `affected_section: "power_flow"` sets `studies.status` to `revision_requested` and (verified by re-invoking the orchestrator) re-enters the graph specifically at the Power Flow node, not from the beginning — reusing the already-correct Site Intelligence and Environmental Permit results rather than recomputing them.
  - Attempting to approve a study that is still `running` (not yet `pending_review`) returns a clear error, not a silent no-op.
  - `POST .../resume` on a study whose process was interrupted mid-run (simulated) correctly continues from the last checkpoint rather than restarting.
  - `pytest services/api/tests/test_human_review.py -v` passes.
- **Commit message:** `feat: implement human review endpoints and study resume`

### Milestone 30 — Document generation (OSS + PDF)

- **Time:** 75–90 min
- **Inputs:** Milestone 29 (an approved study with a full `StudyDocument` from the Regulatory Agent).
- **Outputs:** A real, professionally formatted PDF generated from the `StudyDocument`, uploaded to OSS, with the approve endpoint returning a working download URL.
- **Files:** `services/documents/oss_client.py`, `services/documents/pdf_generator.py`, `services/api/tests/test_documents.py`.
- **Depends on:** Milestone 29.
- **Acceptance criteria:**
  - Approving the real seeded demo study (via the live integration path, reusing Milestone 24's real run) produces a PDF that opens correctly in a standard PDF viewer, includes every section from the `StudyDocument` (site, environmental, power flow, cost, regulatory), and renders the citation list.
  - The PDF is uploaded to OSS under the documented key pattern, and a `documents` row is created referencing it.
  - The `pdf_url` returned by `POST .../approve` is a working, fetchable link (verify with a direct HTTP GET).
  - The PDF generator is confirmed to build entirely from structured `StudyDocument` data (no raw, unsanitized HTML string concatenation) — spot-check the generator code path, per the EDD's security requirement.
  - `pytest services/api/tests/test_documents.py -v` passes.
- **Commit message:** `feat: implement study PDF generation and OSS storage`

---

## Phase 5 — Frontend (Milestones 31–37)

*From this phase onward, the backend from Phase 4 must be running (`docker compose up -d` or local `uvicorn`) for any milestone's acceptance criteria to be checkable — the frontend is built against the real API, never against mocked fixtures, per the EDD's Frontend Architecture decision.*

### Milestone 31 — Next.js scaffold + generated API types

- **Time:** 45–60 min
- **Inputs:** Milestone 30 (a complete, running backend with a stable OpenAPI schema).
- **Outputs:** A running Next.js App Router project with zero custom screens yet, plus generated TypeScript types mirroring every backend Pydantic schema, and a thin API client wrapping `fetch` with the session cookie handled automatically.
- **Files:** `frontend/app/layout.tsx`, `frontend/lib/api-types.ts` (generated, not hand-written), `frontend/lib/api-client.ts`, `frontend/package.json`.
- **Depends on:** Milestone 30.
- **Acceptance criteria:**
  - `npx openapi-typescript <backend-url>/openapi.json -o frontend/lib/api-types.ts` (or equivalent) runs successfully and produces types matching every Pydantic model used in the API responses defined in Phase 4.
  - `npm run dev` serves a blank but running Next.js app with no console errors.
  - A throwaway test call from `api-client.ts` to `GET /api/v1/health` succeeds and is type-checked against the generated types with no `any` casts required.
  - `tsc --noEmit` passes with zero errors.
- **Commit message:** `feat: scaffold Next.js frontend with generated API types`

### Milestone 32 — Design system primitives

- **Time:** 45–60 min
- **Inputs:** Milestone 31.
- **Outputs:** The design tokens (colors, typography scale) wired into Tailwind config, plus the first reusable primitive components, most importantly `ConfidenceBadge`.
- **Files:** `frontend/tailwind.config.ts` (or `.js`), `frontend/components/ui/` (Button, Badge, Card primitives), `frontend/components/ConfidenceBadge.tsx`.
- **Depends on:** Milestone 31.
- **Acceptance criteria:**
  - The exact color values from the EDD's Design System section are present as Tailwind theme extensions (`--color-accent: #3E7BFA`, etc.), not hardcoded inline hex values scattered across components.
  - `ConfidenceBadge` given `0.91`, `0.75`, and `0.55` renders visually distinct green/amber/red states respectively, each with a visible text label (not color alone), confirmed by manual visual check in Storybook or a throwaway test page.
  - Lucide icons are installed and at least one is used correctly in a primitive component, confirming the icon pipeline works end-to-end.
- **Commit message:** `feat: add design system tokens and base UI primitives`

### Milestone 33 — Login screen

- **Time:** 30–45 min
- **Inputs:** Milestone 25 (working `/auth/login` endpoint), Milestone 32 (UI primitives).
- **Outputs:** A working login screen that authenticates against the real backend.
- **Files:** `frontend/app/(auth)/login/page.tsx`.
- **Depends on:** Milestone 25, Milestone 32.
- **Acceptance criteria:**
  - Submitting the seeded Priya credentials in a real browser redirects to `/dashboard` and a valid session cookie is present (check dev tools).
  - Submitting wrong credentials shows a visible error message and does not redirect.
  - Reloading `/dashboard` directly while unauthenticated (no cookie) redirects back to `/login`.
- **Commit message:** `feat: implement login screen`

### Milestone 34 — Dashboard screen

- **Time:** 45–60 min
- **Inputs:** Milestone 26 (working projects endpoint), Milestone 33 (auth gate working).
- **Outputs:** The project queue screen showing the real seeded demo project with a working "Run Study" action.
- **Files:** `frontend/app/dashboard/page.tsx`.
- **Depends on:** Milestone 26, Milestone 33.
- **Acceptance criteria:**
  - After logging in, `/dashboard` displays the real seeded project's name, technology, capacity, and current status badge, sourced live from the API (confirm by changing the project's status directly in the database and reloading — the UI reflects it).
  - Clicking "Run Study" calls `POST /api/v1/projects/{id}/studies` and navigates to `/studies/{study_id}`.
  - The screen visibly (even if non-functionally for MVP) signals it's designed to hold more than one project (e.g., a table structure, not a single hardcoded card).
- **Commit message:** `feat: implement dashboard project queue screen`

### Milestone 35 — Study Live Run screen

- **Time:** 75–90 min
- **Inputs:** Milestone 28 (working SSE endpoint), Milestone 34.
- **Outputs:** The live-updating activity feed and per-agent status chips, driven entirely by the real SSE stream.
- **Files:** `frontend/app/studies/[id]/page.tsx`, `frontend/components/ActivityFeed.tsx`.
- **Depends on:** Milestone 28, Milestone 34.
- **Acceptance criteria:**
  - Triggering a real study run and watching this screen shows agent status chips transitioning `pending → running → succeeded` in real time, matching what's actually happening server-side (cross-check against `agent_runs` rows appearing in the database as the run progresses).
  - The Power Flow Agent's confidence-triggered retry is visibly rendered as a distinct event in the activity feed (not silently absorbed into a single "Power Flow — succeeded" line), confirmed on a run where the retry actually fires.
  - When the study reaches `pending_review`, the screen auto-transitions to the Study Review view (Milestone 36) without a manual page reload.
  - Refreshing the browser mid-run reconnects to the SSE stream (or falls back to polling) and continues showing accurate live state, rather than losing progress.
- **Commit message:** `feat: implement live study run screen with SSE activity feed`

### Milestone 36 — Study Review screen

- **Time:** 75–90 min
- **Inputs:** Milestone 30 (full results + PDF generation), Milestone 35.
- **Outputs:** The full human-review screen: per-agent findings with confidence badges, the persistent escalation banner, citation click-through, the map, and the three terminal actions.
- **Files:** `frontend/app/studies/[id]/page.tsx` (extended), `frontend/components/StudyReviewPanel.tsx`, `frontend/components/GridMap.tsx`.
- **Depends on:** Milestone 30, Milestone 35.
- **Acceptance criteria:**
  - All five agent findings render with correct, live confidence badges pulled from `GET /api/v1/studies/{id}/results`.
  - When the real seeded demo run produces an environmental `review_required: true` flag, the persistent banner appears and the **Approve button is genuinely disabled** (not just styled to look disabled) until the flag is expanded/acknowledged — verify by attempting to trigger the approve action programmatically while the flag is unacknowledged and confirming the backend also rejects it if attempted (defense in depth, not just a UI gate).
  - Clicking a regulatory citation navigates to or reveals the actual retrieved chunk text, matching what's stored in `regulatory_citations`.
  - `GridMap` renders the satellite tile, the AOI polygon, and the wetland/habitat polygon (if any) from real data, not placeholder shapes.
  - Clicking Approve, Reject, and Request Changes each correctly call their respective real endpoints and update the visible study status.
- **Commit message:** `feat: implement study review screen with human-in-the-loop controls`

### Milestone 37 — Audit Trail screen

- **Time:** 45–60 min
- **Inputs:** Milestone 36.
- **Outputs:** The chronological, filterable audit log view with JSON export.
- **Files:** `frontend/app/studies/[id]/audit/page.tsx`.
- **Depends on:** Milestone 36.
- **Acceptance criteria:**
  - Navigating to a completed study's audit trail shows every `tool_call`, `model_call`, `state_transition`, and `human_action` entry in chronological order, matching the raw `audit_log` table contents exactly (spot-check row count).
  - Filtering by actor type (Agent / Orchestrator / Human / System) correctly narrows the visible entries.
  - The "Export JSON" action downloads a file whose contents match `GET /api/v1/studies/{id}/audit-log?format=json`.
- **Commit message:** `feat: implement audit trail screen`

---

## Phase 6 — Deploy & Harden (Milestones 38–40)

### Milestone 38 — Dockerfiles + full docker-compose + nginx

- **Time:** 60–90 min
- **Inputs:** Milestone 37 (a complete, working local system: backend + frontend + all screens).
- **Outputs:** Production-shaped Dockerfiles for the API, frontend, and worker (reserved for future use), a complete `docker-compose.yml` wiring all six services together (api, frontend, postgres, redis, chromadb, nginx), and an Nginx config terminating TLS and reverse-proxying to both app containers.
- **Files:** `infra/docker/Dockerfile.api`, `infra/docker/Dockerfile.frontend`, `infra/docker/Dockerfile.worker`, `docker-compose.yml` (finalized), `infra/nginx/nginx.conf`.
- **Depends on:** Milestone 37.
- **Acceptance criteria:**
  - `docker compose up -d` from a completely clean checkout (no local Python/Node environment needed) brings up the entire stack — all six containers healthy.
  - The full Complete User Journey from the EDD (login → run study → review → approve → download PDF → view audit trail) works end-to-end through Nginx at `http://localhost` (or the configured local domain), not just against the raw `api`/`frontend` container ports.
  - Stopping and restarting the whole stack (`docker compose down && docker compose up -d`) preserves all data (Postgres, Redis, ChromaDB volumes persist correctly).
- **Commit message:** `feat: finalize production Docker Compose stack with Nginx reverse proxy`

### Milestone 39 — CI/CD workflows

- **Time:** 60–75 min
- **Inputs:** Milestone 38 (a fully Dockerized, buildable stack).
- **Outputs:** `ci.yml` (lint, unit tests, integration test against a docker-compose'd test environment with mocked Qwen, Docker image builds) and `deploy.yml` (build, push, SSH deploy, smoke test), both as GitHub Actions workflows.
- **Files:** `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`.
- **Depends on:** Milestone 38.
- **Acceptance criteria:**
  - Opening a pull request with a deliberately broken test (temporarily) causes `ci.yml` to fail visibly in the PR checks; fixing it and re-pushing causes it to pass.
  - `ci.yml` explicitly excludes the live-DashScope integration test from Milestone 24 (verify the workflow run log shows it skipped, not silently run and billed).
  - Merging to `main` triggers `deploy.yml`, which completes successfully and the workflow's own post-deploy smoke test step (hitting `/api/v1/health`) passes.
  - GitHub Actions secrets are used for the ECS SSH key and any registry credentials — confirm none of these values appear in the workflow YAML itself or in any committed file.
- **Commit message:** `ci: add GitHub Actions CI and deploy workflows`

### Milestone 40 — First live deploy + smoke test + rehearsal

- **Time:** 75–90 min
- **Inputs:** Milestone 2 (ECS instance provisioned), Milestone 39 (deploy pipeline working).
- **Outputs:** GridPilot running live on the Alibaba Cloud ECS instance, reachable by public URL, verified to survive a full cold restart, with at least one complete dry-run of the 3-Minute Demo Script from the EDD.
- **Files:** No new files expected; this milestone is a verification and rehearsal pass. If issues are found, fixes land as amendments to files from earlier milestones (e.g., an environment-specific config bug in `infra/nginx/nginx.conf` or `docker-compose.yml`).
- **Depends on:** Milestone 2, Milestone 39.
- **Acceptance criteria:**
  - The deployed public URL serves the full app, and the Complete User Journey works end-to-end against the live Alibaba-hosted instance (not localhost).
  - Rebooting the ECS instance from the Alibaba Cloud console and waiting for Docker Compose's restart policy to bring everything back up automatically results in a working app with no manual intervention — this is the specific cold-restart rehearsal the EDD's Judge Self-Review calls out as a named risk.
  - Running the full 3-Minute Demo Script from the EDD against the live deployment at least three times in a row succeeds each time within the stated timing, including the confidence-triggered Power Flow retry visibly firing during at least one of the three runs.
  - Total DashScope token spend across all rehearsal runs is checked via the `agent_runs` cost-logging fields and confirmed to be trivial (low single-digit dollars at most), per the EDD's Cost Optimization targets.
  - `git tag v1.0-hackathon-demo` is created on the exact commit used for the live demo, so the demonstrated state is pinned and reproducible if judges ask to see the code afterward.
- **Commit message:** `chore: verify production deployment, cold-restart resilience, and demo rehearsal`

---

## After Milestone 40

At this point every "Must Have" item from the EDD's Must Have / Nice to Have / Cut List is built, tested, and running live. If time remains before the demo:

1. Work back through the **Nice to Have** list in the order given in the EDD (revision-loop UI polish, map overlay polish, additional SSE polish, deliberately engineering a visible multi-agent-conflict moment, audit-log export polish) — each of these is a small, scoped addition to an existing milestone's files, not a new milestone, so extend the relevant screen or router directly rather than opening new scope.
2. Re-run Milestone 40's rehearsal checklist after any change, however small — a UI tweak the night before a demo is exactly the kind of change that should still pass the full cold-restart-and-three-dry-runs bar, not be assumed safe because it "should be fine."
3. If something must be cut under real time pressure, cut in the exact order specified in the EDD's **Remove If Time Runs Out** list — that list was written precisely so this decision doesn't have to be made under pressure at 11pm on Day 5.

*End of Implementation Roadmap.*
