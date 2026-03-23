# Semana 2: OpenF1 con API Gateway, Lambda y DynamoDB

## Objetivos

- Exponer datos de la API pública [OpenF1](https://openf1.org/) mediante **API Gateway (HTTP API)** emulado con SAM.
- Ejecutar la lógica en **Lambda** (Python) en local.
- Usar **DynamoDB Local** como **caché** por `session_key`.

## Arquitectura (resumen)

```text
Cliente  GET /drivers?session_key=...
    →  SAM local (HTTP API)
    →  Lambda (handler)
    →  DynamoDB Local (get por session_key)
         ├─ hit  → source: dynamodb
         └─ miss → OpenF1 → put en DynamoDB Local → source: openf1
```

Endpoints: **`GET /drivers`**, **`GET /cache`**.

## Contenido del starter

| Archivo | Rol |
|--------|-----|
| `starter/template.yaml` | Tabla (referencia), Lambda, rutas HTTP, CORS |
| `starter/handler.py` | Caché + OpenF1 |
| `starter/requirements.txt` | `requests` |
| `starter/env.json` | Variables para SAM local + DynamoDB Local |
| `starter/event.json` | Evento para `sam local invoke` |

## Requisitos (local)

- Docker (DynamoDB Local y contenedor de Lambda en SAM).
- AWS CLI (solo para hablar con DynamoDB Local por CLI).
- SAM CLI (`sam --version`).
- Python acorde al runtime del template para `sam build`.

---

## Comandos — solo local (orden sugerido)

Trabaja desde la carpeta **`starter/`** (dentro de `api_gateway_lambda_dynamo`):

```bash
cd starter
```

### 1) Validar y compilar

```bash
cd starter
sam validate --region us-east-1
sam build
```

### 2) DynamoDB Local (terminal aparte; déjala abierta)

```bash
docker run --rm --name ddb-local -p 8000:8000 amazon/dynamodb-local
```

### 3) Crear la tabla en DynamoDB Local (primera vez o contenedor nuevo)

```bash
aws dynamodb create-table \
  --table-name DriversCacheTable-local \
  --attribute-definitions AttributeName=session_key,AttributeType=S \
  --key-schema AttributeName=session_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --endpoint-url http://localhost:8000 \
  --region us-east-1
```

Si la tabla ya existe, puedes ignorar el error de recurso en uso.

### 4) Levantar el API con SAM

```bash
cd starter
sam build
sam local start-api --env-vars env.json
```

Puerto **3000** ocupado:

```bash
lsof -i :3000 -P -n
kill PID_QUE_APAREZCA
```

O usa otro puerto:

```bash
sam local start-api --env-vars env.json --port 3001
```

Si no encuentra `env.json`:

```bash
cd starter
sam local start-api --env-vars "$(pwd)/env.json"
```

### 5) Probar endpoints (ajusta el puerto si usaste `--port 3001`)

```bash
curl -sS -i "http://127.0.0.1:3000/drivers?session_key=9159"

curl -sS "http://127.0.0.1:3000/cache" | jq .
curl -sS "http://127.0.0.1:3000/cache?session_key=9159" | jq .
```

### 6) Ver datos en DynamoDB Local (CLI)

```bash
aws dynamodb list-tables --endpoint-url http://localhost:8000 --region us-east-1

aws dynamodb scan \
  --table-name DriversCacheTable-local \
  --endpoint-url http://localhost:8000 \
  --region us-east-1

aws dynamodb get-item \
  --table-name DriversCacheTable-local \
  --endpoint-url http://localhost:8000 \
  --region us-east-1 \
  --key '{"session_key":{"S":"9159"}}'
```

### 7) Invocar la Lambda sin HTTP API emulado

```bash
cd starter
sam build
sam local invoke F1DriversApiFunction -e event.json --env-vars env.json
```

---

## `env.json` (DynamoDB Local + SAM)

En macOS/Windows el contenedor de Lambda debe llegar al host con **`host.docker.internal`**:

```json
{
  "F1DriversApiFunction": {
    "TABLE_NAME": "DriversCacheTable-local",
    "DYNAMODB_ENDPOINT_URL": "http://host.docker.internal:8000",
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "local",
    "AWS_SECRET_ACCESS_KEY": "local"
  }
}
```

En algunos Linux/Colima, si falla, prueba **`http://172.17.0.1:8000`**.

---

## Solución de problemas (local)

- **URL incorrecta:** usa **`/drivers`** o **`/cache`**, no solo la raíz.
- **`env.json` no existe:** ejecuta SAM desde **`starter/`** o usa `--env-vars "$(pwd)/env.json"`.
- **`scan` en Local vacío pero el API responde con caché:** suele ser que la Lambda no usa Local (revisa el log `[handler] DYNAMODB_ENDPOINT_URL=...` al hacer un GET; no debe estar vacío). Reinicia `sam local start-api` con `--env-vars env.json` tras `sam build`.
- **Puerto 3000 en uso:** libera el proceso o usa `--port 3001` y el `curl` a ese puerto.

## Recursos

- [OpenF1 API](https://openf1.org/)
- [SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html)
- [DynamoDB Local](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html)
