# F1 Drivers API — Local Dev Setup

## Prerequisites
- Docker running
- AWS SAM CLI installed
- AWS CLI installed

---

## Start everything up

All commands run from this directory (`activities/api_gateway_lambda_dynamo/starter/`).

### 1. First time (or after `make stop`)
```bash
make setup
```
Starts DynamoDB Local in Docker and creates the local table.

### 2. Build the Lambda
```bash
make build
```

### 3. Start the local API server
```bash
make start-api
```
Runs on `http://localhost:3000`. Keep this terminal open.

---

## Endpoints

### List pilots from F1 API (no DB touch)
```
GET http://localhost:3000/list?session_key=9158
```

### Import pilots from F1 API → saves to DynamoDB
```
GET http://localhost:3000/drivers?session_key=9158
```

### Read session data from DynamoDB
```
GET http://localhost:3000/cache?session_key=9158
```

> Change `9158` to any valid F1 session key.

---

## Other commands

```bash
# Invoke GET /list once (without starting the full server)
make invoke-list

# Invoke GET /drivers once
make invoke

# Invoke GET /cache once
make invoke-cache

# Stop DynamoDB Local container
make stop
```
