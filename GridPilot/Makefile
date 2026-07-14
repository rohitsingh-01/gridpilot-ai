.PHONY: dev-up dev-down dev-ps test-infra

dev-up:
	docker compose up -d postgres redis chromadb

dev-down:
	docker compose down

dev-ps:
	docker compose ps

test-infra:
	@echo "=== Verifying Postgres ==="
	docker compose exec postgres pg_isready -U gridpilot_app
	@echo "=== Verifying Redis ==="
	docker compose exec redis redis-cli ping
	@echo "=== Verifying ChromaDB ==="
	docker compose exec chromadb python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/api/v1/heartbeat').read().decode())"
