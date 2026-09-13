.PHONY: install browsers test unit integration lint typecheck run-app evidence-run replay

install:
	pip install -e ".[dev]"

browsers:
	python -m playwright install --with-deps chromium

test: unit integration

unit:
	pytest tests/unit -m unit

integration:
	pytest tests/integration -m integration

lint:
	ruff check src tests

typecheck:
	mypy src

# Serve the local fake credit-union app (the proxy target) on :8000
run-app:
	uvicorn cua.target_app.app:app --reload --port 8000

# Run one real LLM-driven discovery run against the live app and write /evidence/
# Requires .env with LLM_PROVIDER + the matching API key.
evidence-run:
	python -m cua.agent.cli discover \
		--goal "look up member 12345 and read their current savings balance" \
		--target http://localhost:8000 \
		--out evidence/discovery_lookup_balance

# Deterministic replay of a saved artifact, no LLM involved.
replay:
	python -m cua.replay.cli run \
		--artifact evidence/discovery_lookup_balance/artifact.json \
		--param member_id=12345 \
		--out evidence/replay_lookup_balance
