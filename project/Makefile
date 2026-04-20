.PHONY: build start stop setup all invoke-ingest invoke-save invoke-sessions invoke-drivers invoke-summary invoke-laps

# AWS profile — leave empty to use the default profile (works for most teammates).
# Juanlu: run make with PROFILE=um_aws  e.g.  make all PROFILE=um_aws
PROFILE ?=
PROFILE_FLAG = $(if $(PROFILE),--profile $(PROFILE),)

# ── Infrastructure ───────────────────────────────────────────────────────────

start:
	docker compose up -d

stop:
	docker compose down

# ── SAM build ────────────────────────────────────────────────────────────────

build:
	sam build $(PROFILE_FLAG)

# ── LocalStack wiring (run after build + start) ──────────────────────────────

setup:
	@chmod +x scripts/setup_localstack.sh
	@AWS_PROFILE=$(PROFILE) ./scripts/setup_localstack.sh

# ── Full local bootstrap (build → start → setup) ─────────────────────────────

all: build start
	@echo "Waiting for services to be ready..."
	@sleep 8
	@$(MAKE) setup PROFILE=$(PROFILE)

# ── Individual lambda invocations ─────────────────────────────────────────────

invoke-ingest:
	sam local invoke IngestSessionFunction \
		--event lambdas/ingest_session/events/event.json \
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
