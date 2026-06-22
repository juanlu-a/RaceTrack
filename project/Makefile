.PHONY: build start stop setup setup-simulation all start-api \
	invoke-ingest invoke-worker invoke-save invoke-sessions invoke-drivers \
	invoke-summary invoke-laps invoke-start-simulation demo-simulation

# AWS profile — leave empty to use the default profile (works for most teammates).
# Juanlu: run make with PROFILE=um_aws  e.g.  make all PROFILE=um_aws
PROFILE ?=
PROFILE_FLAG = $(if $(PROFILE),--profile $(PROFILE),)

API_BASE ?= http://localhost:3000
SESSION_KEY ?= 9158
SIM_DURATION ?= 120

# ── Infrastructure ───────────────────────────────────────────────────────────

# Core infra without f1-consumer (consumer needs .local/simulation.env first).
start-core:
	docker compose up -d localstack postgres metrics-exporter prometheus grafana
	@echo "Waiting for services..."
	@sleep 8

start: start-core setup-simulation
	docker compose up -d f1-consumer

stop:
	docker compose down

# ── SAM build ────────────────────────────────────────────────────────────────

build:
	sam build $(PROFILE_FLAG)

# ── LocalStack wiring (run after build + start-core) ─────────────────────────

setup:
	@chmod +x scripts/setup_localstack.sh
	@AWS_PROFILE=$(PROFILE) ./scripts/setup_localstack.sh

setup-simulation:
	@chmod +x scripts/setup_simulation_local.sh scripts/wait_for_ingest.sh
	@./scripts/setup_simulation_local.sh

# ── Full local bootstrap (build → infra → LocalStack + simulation) ───────────

all: build start-core setup setup-simulation
	docker compose up -d f1-consumer

# ── Local API server (Postman / curl) ────────────────────────────────────────

start-api:
	sam local start-api \
		--env-vars env.json \
		--port 3000 \
		$(PROFILE_FLAG)

# ── End-to-end local demo: ingest → wait → simulate → Grafana ────────────────
# Requires: make all  AND  make start-api (in another terminal)

demo-simulation:
	@echo "▶ Ingest session $(SESSION_KEY)..."
	@curl -sS "$(API_BASE)/ingest?session_key=$(SESSION_KEY)"; echo
	@API_BASE="$(API_BASE)" ./scripts/wait_for_ingest.sh "$(SESSION_KEY)"
	@echo "▶ Start simulation (duration=$(SIM_DURATION)s metadata)..."
	@curl -sS -X POST "$(API_BASE)/start-simulation" \
		-H "Content-Type: application/json" \
		-d '{"session_id":"$(SESSION_KEY)","simulation_duration_seconds":$(SIM_DURATION)}'; echo
	@echo ""
	@echo "Done. In ~30s open Grafana: http://localhost:3001"
	@echo "  Dashboard: RaceTrack — F1 Telemetry"
	@echo "  Pick a Simulation from the dropdown (refresh 5s)"
	@echo "  Metrics raw: http://localhost:9100/metrics"

# ── Individual lambda invocations ─────────────────────────────────────────────

invoke-ingest:
	sam local invoke IngestSessionFunction \
		--event lambdas/ingest_session/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-worker:
	sam local invoke IngestWorkerFunction \
		--event lambdas/ingest_worker/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-save:
	sam local invoke SaveSessionFunction \
		--event lambdas/save_session/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-sessions:
	sam local invoke ListSessionFunction \
		--event lambdas/list_session/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-drivers:
	sam local invoke ListDriversFunction \
		--event lambdas/list_drivers/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-summary:
	sam local invoke DriverSummaryFunction \
		--event lambdas/driver_summary/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-laps:
	sam local invoke DriverLapsFunction \
		--event lambdas/driver_laps/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)

invoke-start-simulation:
	sam local invoke StartSimulationFunction \
		--event lambdas/start_simulation/events/event.json \
		--env-vars env.json \
		$(PROFILE_FLAG)
