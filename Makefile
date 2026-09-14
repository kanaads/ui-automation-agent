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

# Serve the local fake credit-union app (the proxy target) on :8000.
# create_app() is a factory (it takes tenant_variant, defaulting to the
# base tenant) rather than a module-level `app`, so --factory is required.
run-app:
	uvicorn cua.target_app.app:create_app --factory --reload --port 8000

# Run one real LLM-driven discovery run against the live app and write /evidence/
# Requires .env with LLM_PROVIDER + the matching API key. Member 10001 is a
# real seed record (src/cua/target_app/data.py) -- 12345 is not, and a
# discovery goal naming a member that doesn't exist never reaches a
# checkpoint, so no artifact is ever recorded to replay in the next step.
evidence-run:
	python -m cua.agent.cli discover \
		--goal "look up member 10001 and open their detail page" \
		--target http://localhost:8000 \
		--out evidence/discovery_lookup_balance \
		--capability-id look_up_member_balance \
		--description "Look up a member by id and open their detail page (where their current savings balance is shown)." \
		--checkpoint-role heading --checkpoint-name "Member Detail" \
		--parameterize 10001=member_id

# Deterministic replay of a saved artifact, no LLM involved. --start-path
# must match discovery's own (the artifact's steps were recorded relative
# to whatever screen that path lands on) -- replay's own default (/nav)
# is for artifacts recorded starting there instead, e.g. in this
# project's own tests.
replay:
	python -m cua.replay.cli run \
		--artifact evidence/discovery_lookup_balance/artifact.json \
		--target http://localhost:8000 \
		--start-path /app \
		--param member_id=10002 \
		--out evidence/replay_lookup_balance
