#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_localstack.sh
# Deploys SaveSessionFunction into LocalStack and wires up the EventBridge
# rule so that ingest_session → EventBridge → save_session works locally.
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
FUNCTION_NAME="SaveSessionFunction"
RULE_NAME="SessionIngestedRule"
ZIP_PATH="scripts/save_session_lambda.zip"
BUILD_DIR=".aws-sam/build/${FUNCTION_NAME}"

# ── 0. Sanity check ─────────────────────────────────────────────────────────
if [ ! -d "$BUILD_DIR" ]; then
  echo "ERROR: Build directory '$BUILD_DIR' not found."
  echo "       Run 'sam build --profile um_aws' first."
  exit 1
fi

# ── 1. Package Lambda artifact ───────────────────────────────────────────────
echo "Packaging ${FUNCTION_NAME}..."
rm -f "$ZIP_PATH"
(cd "$BUILD_DIR" && zip -qr "../../../${ZIP_PATH}" .)
echo "  -> ${ZIP_PATH}"

# ── 2. Wait for LocalStack lambda service to be ready ───────────────────────
echo "Waiting for LocalStack (lambda)..."
until curl -sf "$ENDPOINT/_localstack/health" \
    | python3 -c "import sys,json; s=json.load(sys.stdin).get('services',{}); exit(0 if s.get('lambda') in ('running','available') else 1)" \
    2>/dev/null; do
  printf "."
  sleep 2
done
echo " ready."

# ── 3. S3 bucket ─────────────────────────────────────────────────────────────
echo "Creating S3 bucket..."
aws --endpoint-url="$ENDPOINT" --region="$REGION" \
    s3 mb s3://racetrack-sessions 2>/dev/null || echo "  (already exists)"

# ── 4. IAM role (LocalStack doesn't enforce permissions, just needs an ARN) ──
echo "Creating IAM role..."
aws --endpoint-url="$ENDPOINT" --region="$REGION" iam create-role \
    --role-name lambda-exec \
    --assume-role-policy-document \
    '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    2>/dev/null || echo "  (already exists)"

ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/lambda-exec"

# ── 5. Deploy Lambda ──────────────────────────────────────────────────────────
# DB_HOST=postgres  → container name, reachable inside the racetrack network
# S3_ENDPOINT=http://localstack:4566 → container-to-container
echo "Deploying ${FUNCTION_NAME} to LocalStack..."

ENV_VARS="Variables={\
S3_ENDPOINT=http://localstack:4566,\
DB_HOST=postgres,\
DB_PORT=5432,\
DB_NAME=racetrack,\
DB_USER=racetrack,\
DB_PASSWORD=racetrack,\
AWS_ACCESS_KEY_ID=test,\
AWS_SECRET_ACCESS_KEY=test,\
AWS_DEFAULT_REGION=${REGION}\
}"

if aws --endpoint-url="$ENDPOINT" --region="$REGION" \
       lambda get-function --function-name "$FUNCTION_NAME" &>/dev/null; then
  # Update existing function
  aws --endpoint-url="$ENDPOINT" --region="$REGION" \
      lambda update-function-code \
      --function-name "$FUNCTION_NAME" \
      --zip-file "fileb://${ZIP_PATH}" >/dev/null
  aws --endpoint-url="$ENDPOINT" --region="$REGION" \
      lambda update-function-configuration \
      --function-name "$FUNCTION_NAME" \
      --environment "$ENV_VARS" >/dev/null
  echo "  (updated)"
else
  # Create new function
  aws --endpoint-url="$ENDPOINT" --region="$REGION" \
      lambda create-function \
      --function-name "$FUNCTION_NAME" \
      --runtime python3.9 \
      --handler handler.handler \
      --zip-file "fileb://${ZIP_PATH}" \
      --role "$ROLE_ARN" \
      --timeout 60 \
      --memory-size 512 \
      --environment "$ENV_VARS" >/dev/null
  echo "  (created)"
fi

LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT}:function:${FUNCTION_NAME}"

# ── 6. EventBridge rule ───────────────────────────────────────────────────────
echo "Creating EventBridge rule '${RULE_NAME}'..."
aws --endpoint-url="$ENDPOINT" --region="$REGION" events put-rule \
    --name "$RULE_NAME" \
    --event-pattern '{"source":["racetrack"],"detail-type":["SessionIngested"]}' \
    --state ENABLED >/dev/null

# ── 7. Lambda target ──────────────────────────────────────────────────────────
echo "Setting Lambda as EventBridge target..."
aws --endpoint-url="$ENDPOINT" --region="$REGION" events put-targets \
    --rule "$RULE_NAME" \
    --targets "[{\"Id\":\"SaveSession\",\"Arn\":\"${LAMBDA_ARN}\"}]" >/dev/null

# ── 8. Lambda permission for EventBridge ─────────────────────────────────────
echo "Granting EventBridge permission to invoke Lambda..."
aws --endpoint-url="$ENDPOINT" --region="$REGION" lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id EventBridgeInvoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT}:rule/${RULE_NAME}" \
    2>/dev/null || echo "  (permission already exists)"

echo ""
echo "LocalStack setup complete."
echo "  S3 bucket   : s3://racetrack-sessions (endpoint: ${ENDPOINT})"
echo "  Lambda      : ${LAMBDA_ARN}"
echo "  Rule        : ${RULE_NAME}"
echo ""
echo "Full local flow:"
echo "  ingest_session (sam local invoke) -> S3 + EventBridge -> save_session (LocalStack) -> Postgres"
