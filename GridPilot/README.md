# GridPilot

Autonomous Grid Interconnection Planning Agent.

## Infrastructure Setup

GridPilot depends on the following infrastructure components:
- **PostgreSQL 16**: Primary relational database for configuration, grid topology, project files, studies, agent execution logs, and audit logs.
- **Redis 7**: Cache and session store.
- **ChromaDB**: Vector database for semantic memory, storing tariff corpora, environmental filing precedents, and historical study outcomes.

### Requirements
- Docker and Docker Compose installed locally.

### Standing up Infrastructure (Milestone 1)
Run the following command to start Postgres, Redis, and ChromaDB containers:
```bash
docker compose up -d postgres redis chromadb
```
Or use the Makefile shortcut:
```bash
make dev-up
```

### Verification
To verify the setup, run the Makefile check:
```bash
make test-infra
```
Or manually run:
- Postgres check: `pg_isready -h localhost -p 5432 -U gridpilot_app`
- Redis check: `redis-cli -h localhost ping`
- ChromaDB check: `curl -s -f http://localhost:8001/api/v1/heartbeat`

## Directory Structure
The repository is structured as follows:
- `agents/`: Swarm of narrow LLM and simulation agents.
- `services/`: API layer, databases, document generation, and memory storage.
- `shared/`: Cross-cutting schemas and common types.
- `data/`: Seed scripts, raw environmental datasets, and tariff corpora.
- `frontend/`: Next.js web review dashboard.
- `infra/`: Docker files, reverse-proxy configs, and cloud deployment scripts.
- `tests/`: Integration and unit tests.
