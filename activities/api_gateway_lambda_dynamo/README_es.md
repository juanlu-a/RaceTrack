# Semana 2: OpenF1 con API Gateway, Lambda y DynamoDB

## Objetivos

- Exponer datos de la API pública [OpenF1](https://openf1.org/) mediante **API Gateway (HTTP API)**.
- Ejecutar la lógica en **Lambda** (Python).
- Usar **DynamoDB** como **caché** por `session_key`: la primera petición obtiene pilotos desde OpenF1 y los guarda; las siguientes leen la tabla (menos latencia y menos llamadas externas).

## Arquitectura (resumen)

```text
Cliente  GET /drivers?session_key=...
    →  API Gateway (HTTP API)
    →  Lambda (handler)
    →  DynamoDB (get por session_key)
         ├─ hit  → respuesta desde caché (source: dynamodb)
         └─ miss → GET OpenF1 → put en DynamoDB → respuesta (source: openf1)
```

## Contenido del starter

| Archivo | Rol |
|--------|-----|
| `starter/template.yaml` | Tabla DynamoDB, Lambda, evento HTTP API `GET /drivers`, CORS, outputs |
| `starter/handler.py` | Lógica de caché + llamada a OpenF1 |
| `starter/requirements.txt` | Dependencia `requests` (boto3 va con el runtime de Lambda) |

## Requisitos

- AWS CLI y SAM CLI configurados (`sam --version`).
- Python acorde al runtime del template (p. ej. 3.12) para `sam build` en local.

## Despliegue

Desde la carpeta `starter`:

```bash
sam build
sam deploy --guided
```

Anota en los **Outputs** de CloudFormation:

- `ApiEndpoint`: URL base del API.
- `DriversTableName`: nombre de la tabla DynamoDB.

## Probar en local con `sam local invoke`

`sam local invoke` ejecuta la Lambda en Docker, pero **sigue usando DynamoDB en la nube** (no hay tabla “dentro” del contenedor). Si ves:

`ResourceNotFoundException` / `Requested resource not found`

significa que el **`TABLE_NAME` de `env.json` no coincide con ninguna tabla en tu cuenta de AWS**.

**Opción A — Ya desplegaste con `sam deploy`:** copia el output **`DriversTableName`** de CloudFormation y ponlo en `starter/env.json`:

```json
{
  "F1DriversApiFunction": {
    "TABLE_NAME": "tu-stack-DriversCacheTable-XXXXXXXX"
  }
}
```

**Opción B — Tabla solo para pruebas locales:** crea una tabla con el mismo esquema que el template (clave `session_key` tipo string) y el nombre que uses en `env.json`, por ejemplo:

```bash
aws dynamodb create-table \
  --table-name DriversCacheTable-local \
  --attribute-definitions AttributeName=session_key,AttributeType=S \
  --key-schema AttributeName=session_key,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

(Ajusta `--region` a la región donde usas DynamoDB.) Luego deja `"TABLE_NAME": "DriversCacheTable-local"` en `env.json`.

Comando de prueba (desde `starter`):

```bash
sam build
sam local invoke F1DriversApiFunction -e event.json --env-vars env.json
```

## Probar el endpoint

Sustituye `API_URL` por el valor de `ApiEndpoint` (sin barra final o con ella, según lo que muestre la consola):

```bash
curl -sS "${API_URL}/drivers?session_key=9159" | jq .
```

- Primera llamada: `"source": "openf1"` y se crea el ítem en DynamoDB.
- Segunda llamada con el mismo `session_key`: `"source": "dynamodb"` y el mismo listado de pilotos.

## Conceptos clave

- **HTTP API vs REST API**: aquí se usa HTTP API (más simple y barato para casos como este).
- **Evento de API Gateway v2**: en Lambda, `queryStringParameters` lleva `session_key`.
- **IAM**: la plantilla usa `DynamoDBCrudPolicy` para que la función pueda leer y escribir solo esa tabla.
- **Pay-per-request**: la tabla está en modo on-demand; adecuado para prácticas y cargas irregulares.

## Extensiones posibles (opcional)

- Invalidar caché borrando el ítem en DynamoDB o añadiendo TTL (`expires_at`).
- Endpoint `DELETE /drivers/{session_key}` para vaciar caché.
- Paginación o filtro si más adelante guardas más tipos de datos de OpenF1.

## Recursos

- [OpenF1 API](https://openf1.org/)
- [SAM: HttpApi](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-httpapi.html)
- [DynamoDB con Lambda](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBMapper.Methods.html) (patrones de acceso)
