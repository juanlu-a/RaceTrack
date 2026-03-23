AWS_LOCAL = AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local AWS_DEFAULT_REGION=us-east-2

.PHONY: build invoke start-api

build:
	sam build

invoke: build
	$(AWS_LOCAL) sam local invoke DriverSummaryFunction \
		--event events/event.json \
		--skip-pull-image

start-api: build
	$(AWS_LOCAL) sam local start-api
