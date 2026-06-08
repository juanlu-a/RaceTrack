# Week 4: S3, DynamoDB, and EventBridge with CDK

## Objectives
- Migrate from SAM to CDK for infrastructure as code
- Create DynamoDB tables for session and driver data
- Store raw data in S3
- Configure EventBridge rule to trigger Lambda on schedule
- Implement repository pattern for data access

## Tools
- AWS CDK (Python), DynamoDB, S3, EventBridge

## Activity
1. Create CDK stacks for data storage (DynamoDB tables + S3 bucket)
2. Implement repository classes for DynamoDB and S3 operations
3. Wire EventBridge rule to trigger ingestion Lambda
4. Store ingested data in both S3 (raw) and DynamoDB (parsed)

## Steps

### 1. Set up CDK project
From the `RaceTrack` repo root:
```bash
cd activities/part-1/week-04-data-storage/cdk
python3 -m pip install -r requirements.txt
npx aws-cdk@2 synth
```

### 2. Create DataStack
Define DynamoDB tables:
- `f1_sessions` — PK: session_key (Number)
- `f1_driver_stats` — PK: session_key (Number), SK: driver_number (Number)

Define S3 bucket:
- `f1-raw-data` for storing raw API responses

### 3. Implement repositories
Create repository classes that use boto3 to interact with DynamoDB and S3.
Use `AWS_ENDPOINT_URL` environment variable for LocalStack compatibility.

### 4. Create MessagingStack
Define EventBridge rule that triggers every 5 seconds (disabled by default).

### 5. Test with LocalStack (this repo)
This repository has no `localstack/` folder and no `Makefile` under `week-04-data-storage`. LocalStack is started from **`project/`**:

```bash
cd project
make start
```

(See `project/HOWTO.md` for the full flow, e.g. `make all` after SAM is configured.)

Environment variables for boto3 against LocalStack:

```bash
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
```

Install repositories and verify the import. The path to `starter` depends on **your current directory**:

From the **repo root** `RaceTrack`:

```bash
python3 -m pip install -e activities/part-1/week-04-data-storage/starter
```

From **`project/`** (where `make start` lives), go up one level:

```bash
python3 -m pip install -e ../activities/part-1/week-04-data-storage/starter
```

Then:

```bash
python3 -c "from repositories.session_repo import SessionRepository; print('OK')"
```

Do not paste markdown **triple backtick** fences into the shell; in zsh you may get a `bquote>` prompt. Type only the `export ...` lines without markdown.

For real DynamoDB calls in LocalStack, create the tables first (deploy `DataStack` to LocalStack or use the AWS CLI with `--endpoint-url`).

## Key Concepts
- **CDK vs SAM**: CDK uses real programming languages, SAM uses YAML templates
- **CDK Stacks**: Logical grouping of resources
- **Repository Pattern**: Abstraction layer over data access
- **EventBridge Rules**: Schedule or event-pattern based triggers
- **DynamoDB Partition/Sort Keys**: Efficient data access patterns
