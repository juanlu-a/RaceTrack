# ──────────────────────────────────────────────────────────────────────────────
# Local dev: DynamoDB Local (Docker) + SAM CLI
# ──────────────────────────────────────────────────────────────────────────────
NETWORK         = racetrack-local
DYNAMO_URL      = http://localhost:8000
TABLE           = DriversCacheTable-local

# Dummy creds so SAM/boto3 don't try to hit real AWS when running locally.
# DynamoDB Local doesn't validate credentials, so any value works.
AWS_LOCAL       = AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=us-east-2

.PHONY: build setup create-table invoke start-api stop

## sam build — compile dependencies into .aws-sam/
build:
	sam build

## Start DynamoDB Local container and create the table
setup:
	docker compose up -d
	@echo "Waiting for DynamoDB Local..."
	@sleep 2
	$(MAKE) create-table

## Create the local DynamoDB table (idempotent — safe to run twice)
create-table:
	$(AWS_LOCAL) aws dynamodb create-table \
		--table-name $(TABLE) \
		--attribute-definitions AttributeName=session_key,AttributeType=S \
		--key-schema AttributeName=session_key,KeyType=HASH \
		--billing-mode PAY_PER_REQUEST \
		--endpoint-url $(DYNAMO_URL) 2>/dev/null \
	&& echo "Table '$(TABLE)' created." \
	|| echo "Table '$(TABLE)' already exists — skipping."

## Run a single Lambda invocation using event.json
invoke: build
	$(AWS_LOCAL) sam local invoke F1DriversApiFunction \
		--event event.json \
		--env-vars env.json \
		--docker-network $(NETWORK)

## Start a local HTTP API on http://localhost:3000
start-api: build
	$(AWS_LOCAL) sam local start-api \
		--env-vars env.json \
		--docker-network $(NETWORK)

## Stop and remove the DynamoDB Local container
stop:
	docker compose down
