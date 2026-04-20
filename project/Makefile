.PHONY: build start stop setup all invoke-ingest invoke-sessions invoke-drivers invoke-summary invoke-laps

# ── Infrastructure ───────────────────────────────────────────────────────────

start:
	docker compose up -d

stop:
	docker compose down

# ── SAM build ────────────────────────────────────────────────────────────────

build:
	sam build --profile um_aws

# ── LocalStack wiring (run after build + start) ──────────────────────────────

setup:
	@chmod +x scripts/setup_localstack.sh
	@./scripts/setup_localstack.sh

# ── Full local bootstrap (build → start → setup) ─────────────────────────────

all: build start
	@echo "Waiting for services to be ready..."
	@sleep 8
	@$(MAKE) setup

# ── Individual lambda invocations ─────────────────────────────────────────────

invoke-ingest:
	sam local invoke IngestSessionFunction \
		--event lambdas/ingest_session/events/event.json \
		--env-vars env.json \
		--profile um_aws

invoke-save:
	sam local invoke SaveSessionFunction \
		--event lambdas/save_session/events/event.json \
		--env-vars env.json \
		--profile um_aws

invoke-sessions:
	sam local invoke ListSessionFunction \
		--event lambdas/list_session/events/event.json \
		--env-vars env.json \
		--profile um_aws

invoke-drivers:
	sam local invoke ListDriversFunction \
		--event lambdas/list_drivers/events/event.json \
		--env-vars env.json \
		--profile um_aws

invoke-summary:
	sam local invoke DriverSummaryFunction \
		--event lambdas/driver_summary/events/event.json \
		--env-vars env.json \
		--profile um_aws

invoke-laps:
	sam local invoke DriverLapsFunction \
		--event lambdas/driver_laps/events/event.json \
		--env-vars env.json \
		--profile um_aws
