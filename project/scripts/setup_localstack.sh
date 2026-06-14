#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_localstack.sh
# Deploys the event-driven lambdas into LocalStack and wires up the EventBridge
# rules so the full async flow works locally:
#
#   ingest_session (sam local invoke / start-api)
#       -> EventBridge(IngestRequested) -> IngestWorkerFunction (LocalStack)
#       -> S3 + EventBridge(SessionIngested) -> SaveSessionFunction (LocalStack)
#       -> Postgres
#
# Run from the project/ directory AFTER sam build and docker compose up -d.
# ---------------------------------------------------------------------------
set -euo pipefail

# AWS_PROFILE is passed in from the Makefile (via make setup PROFILE=um_aws).
# Makefile sets AWS_PROFILE= when PROFILE is empty; that breaks AWS CLI with
# "The config profile () could not be found". For LocalStack we need no profile.
if [ -n "${AWS_PROFILE:-}" ]; then
  export AWS_PROFILE
else
  unset AWS_PROFILE
fi

ENDPOINT="http://localhost:4566"
REGION="us-east-1"
ACCOUNT="000000000000"
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/lambda-exec"

awslocal() {
  aws --endpoint-url="$ENDPOINT" --region="$REGION" "$@"
}

# ── Deploy (create or update) a Lambda from its sam build artifact ──────────
# Usage: deploy_lambda <FunctionName> <timeout> <memory>
deploy_lambda() {
  local function_name="$1"
  local timeout="$2"
  local memory="$3"
  local build_dir=".aws-sam/build/${function_name}"
  local zip_path="scripts/${function_name}.zip"

  if [ ! -d "$build_dir" ]; then
    echo "ERROR: Build directory '$build_dir' not found. Run 'sam build' first."
    exit 1
  fi

  echo "Packaging ${function_name}..."
  rm -f "$zip_path"
  (cd "$build_dir" && zip -qr "../../../${zip_path}" .)

  local env_vars="Variables={\
S3_BUCKET_NAME=racetrack-sessions,\
S3_ENDPOINT=http://localstack:4566,\
EVENTS_ENDPOINT=http://localstack:4566,\
DB_HOST=postgres,\
DB_PORT=5432,\
DB_NAME=racetrack,\
DB_USER=racetrack,\
DB_PASSWORD=racetrack,\
AWS_ACCESS_KEY_ID=test,\
AWS_SECRET_ACCESS_KEY=test,\
AWS_DEFAULT_REGION=${REGION}\
}"

  if awslocal lambda get-function --function-name "$function_name" &>/dev/null; then
    awslocal lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://${zip_path}" >/dev/null
    awslocal lambda update-function-configuration \
        --function-name "$function_name" \
        --timeout "$timeout" --memory-size "$memory" \
        --environment "$env_vars" >/dev/null
    echo "  ${function_name} (updated)"
  else
    awslocal lambda create-function \
        --function-name "$function_name" \
        --runtime python3.9 \
        --handler handler.handler \
        --zip-file "fileb://${zip_path}" \
        --role "$ROLE_ARN" \
        --timeout "$timeout" \
        --memory-size "$memory" \
        --environment "$env_vars" >/dev/null
    echo "  ${function_name} (created)"
  fi
}

# ── Wire an EventBridge rule to a Lambda target ─────────────────────────────
# Usage: wire_rule <RuleName> <event-pattern-json> <FunctionName> <TargetId>
wire_rule() {
  local rule_name="$1"
  local pattern="$2"
  local function_name="$3"
  local target_id="$4"
  local lambda_arn="arn:aws:lambda:${REGION}:${ACCOUNT}:function:${function_name}"

  awslocal events put-rule \
      --name "$rule_name" \
      --event-pattern "$pattern" \
      --state ENABLED >/dev/null

  awslocal events put-targets \
      --rule "$rule_name" \
      --targets "[{\"Id\":\"${target_id}\",\"Arn\":\"${lambda_arn}\"}]" >/dev/null

  awslocal lambda add-permission \
      --function-name "$function_name" \
      --statement-id "EventBridgeInvoke-${rule_name}" \
      --action lambda:InvokeFunction \
      --principal events.amazonaws.com \
      --source-arn "arn:aws:events:${REGION}:${ACCOUNT}:rule/${rule_name}" \
      2>/dev/null || true
  echo "  rule ${rule_name} -> ${function_name}"
}

# ── 1. Wait for LocalStack lambda service to be ready ───────────────────────
echo "Waiting for LocalStack (lambda)..."
until curl -sf "$ENDPOINT/_localstack/health" \
    | python3 -c "import sys,json; s=json.load(sys.stdin).get('services',{}); exit(0 if s.get('lambda') in ('running','available') else 1)" \
    2>/dev/null; do
  printf "."
  sleep 2
done
echo " ready."

# ── 2. S3 bucket ─────────────────────────────────────────────────────────────
echo "Creating S3 bucket..."
awslocal s3 mb s3://racetrack-sessions 2>/dev/null || echo "  (already exists)"

# ── 3. IAM role (LocalStack doesn't enforce permissions, just needs an ARN) ──
echo "Creating IAM role..."
awslocal iam create-role \
    --role-name lambda-exec \
    --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    2>/dev/null || echo "  (already exists)"

# ── 4. Deploy event-driven lambdas ──────────────────────────────────────────
echo "Deploying lambdas to LocalStack..."
deploy_lambda "IngestWorkerFunction" 900 512
deploy_lambda "SaveSessionFunction" 60 512

# ── 5. EventBridge rules ─────────────────────────────────────────────────────
echo "Wiring EventBridge rules..."
wire_rule "IngestRequestedRule" \
    '{"source":["racetrack"],"detail-type":["IngestRequested"]}' \
    "IngestWorkerFunction" "IngestWorker"
wire_rule "SessionIngestedRule" \
    '{"source":["racetrack"],"detail-type":["SessionIngested"]}' \
    "SaveSessionFunction" "SaveSession"

echo ""
echo "LocalStack setup complete."
echo "  S3 bucket : s3://racetrack-sessions (endpoint: ${ENDPOINT})"
echo "  Lambdas   : IngestWorkerFunction, SaveSessionFunction"
echo "  Rules     : IngestRequestedRule, SessionIngestedRule"
echo ""
echo "Full local flow:"
echo "  ingest_session (HTTP/sam) -> EventBridge(IngestRequested) -> IngestWorkerFunction"
echo "    -> S3 + EventBridge(SessionIngested) -> SaveSessionFunction -> Postgres"
