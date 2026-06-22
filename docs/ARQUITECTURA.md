# RaceTrack — Arquitectura (resumen)

**¿Qué hace el proyecto?** Toma datos reales de una sesión de Fórmula 1 (API pública
[OpenF1](https://openf1.org)), los guarda, los "reproduce" como una simulación acelerada, calcula
métricas por piloto y las muestra en vivo en un tablero de **Grafana**.

- **Cuenta AWS:** `190914649240` · **Región:** `us-east-1`
- **Dos entornos iguales:** `staging` (pruebas) y `prod` (producción). Misma cuenta, separados por
  el prefijo de nombres `racetrack-<entorno>-*`.
- **Infra como código:** Terraform · **Despliegue:** GitHub Actions (push a `staging` despliega
  staging; push a `main` despliega prod y crea la etiqueta `version_X.Y.Z`).

---

## 1. Cómo funciona, paso a paso

Hay **dos fases**: primero _cargar_ una sesión, después _simularla_ y _verla_.

```mermaid
flowchart TD
    user([Vos / curl]) -->|"1 - GET /ingest"| API[API Gateway]
    user -->|"4 - POST /start-simulation"| API

    API --> ING[Lambda ingest_session]
    API --> START[Lambda start_simulation]

    ING -->|evento| WORK[Lambda ingest_worker]
    WORK -->|baja los datos| OPENF1[(API OpenF1)]
    WORK -->|guarda crudo| S3[(S3)]
    WORK -->|evento| SAVE[Lambda save_session]
    SAVE -->|"2 - guarda ordenado"| RDS[(Base de datos RDS)]

    START -->|"3 - lee la sesion"| RDS
    START -->|"5 - 1 mensaje cada 10s de carrera"| SQS[[Cola SQS]]
    SQS --> CONS[f1-consumer]
    CONS -->|"6 - metricas por piloto"| DDB[(DynamoDB)]

    DDB --> EXP[metrics-exporter]
    EXP -->|"7 - scrape"| PROM[Prometheus]
    PROM -->|"8 - consulta"| GRAF[Grafana]
    GRAF --> ojo([Tu navegador])
```

**En palabras simples:**

1. **Cargar la sesión** → `GET /ingest?session_key=9158`. Responde al toque (`202`) y sigue
   trabajando solo por detrás.
2. Por detrás: `ingest_worker` baja los datos de OpenF1 y los deja en **S3**; después
   `save_session` los ordena y los guarda en la base de datos **RDS**. (Tarda ~30–60s la primera vez.)
3. **Simular** → `POST /start-simulation` con `{session_id, simulation_duration_seconds}`.
4. `start_simulation` lee la sesión de RDS, la corta en **bloques de 10 segundos de carrera** y
   manda **un mensaje por bloque** a la cola **SQS**.
5. **f1-consumer** va leyendo la cola y calcula las métricas de cada piloto, guardándolas en
   **DynamoDB**.
6. **metrics-exporter** lleva el "reloj" de la simulación y publica las métricas del momento actual.
7. **Prometheus** las recoge y **Grafana** las dibuja en el tablero _RaceTrack — F1 Telemetry_.

> 💡 La simulación comprime toda la carrera en los minutos que le pidas
> (`simulation_duration_seconds`, ej. 300 = 5 minutos).

---

## 2. Qué servicios de AWS usamos (y dónde viven)

Pensalo en **3 grupos**: lo que mira a internet, lo que está dentro de la red privada (VPC) y los
servicios de almacenamiento.

```mermaid
flowchart TB
    internet([Internet])

    subgraph fuera["Sin VPC (serverless)"]
        API[API Gateway]
        EB{{EventBridge}}
        LAMBDAS[8 Lambdas<br/>ingesta + lectura + simulacion]
    end

    subgraph aws["Servicios AWS regionales"]
        S3[(S3<br/>datos crudos)]
        DDB[(DynamoDB<br/>metricas)]
        SQS[[SQS + DLQ]]
        ECR[(ECR<br/>imagenes)]
        CW[(CloudWatch<br/>logs)]
    end

    subgraph vpc["VPC default 172.31.0.0/16 (sin NAT)"]
        subgraph pub["Subredes PUBLICAS"]
            ALB[ALB publico :80]
            RDS[(RDS PostgreSQL :5432)]
        end
        subgraph priv["Subredes PRIVADAS (sin IP publica)"]
            GW{{Gateway endpoints<br/>S3 + DynamoDB}}
            IF{{Interface endpoints<br/>ECR + Logs + SQS}}
            subgraph ecs["Cluster ECS Fargate"]
                CONS[f1-consumer]
                EXP[metrics-exporter :9100]
                PROM[Prometheus :9090]
                GRAF[Grafana :3000]
            end
        end
    end

    internet --> API
    internet -->|"Grafana - con login"| ALB --> GRAF
    internet -->|":5432 - con contrasena"| RDS

    API --> LAMBDAS
    LAMBDAS <--> EB
    LAMBDAS --> S3
    LAMBDAS --> RDS
    LAMBDAS --> SQS

    SQS --> CONS --> DDB
    EXP --> DDB
    PROM -->|scrape| EXP
    GRAF -->|consulta| PROM

    %% egress de las tareas a AWS por la red interna (sin internet)
    ecs -.red interna.-> GW
    ecs -.red interna.-> IF
    GW -.-> S3
    GW -.-> DDB
    IF -.-> ECR
    IF -.-> CW
    IF -.-> SQS
```

### Zoom a la red (VPC, subredes y endpoints)

```mermaid
flowchart TB
    subgraph vpc["VPC default - 172.31.0.0/16 - sin Internet Gateway para lo privado"]
        direction TB

        subgraph pub["Subredes PUBLICAS (default-for-az, 1 por AZ)"]
            ALB[ALB internet-facing]
            RDS[(RDS PostgreSQL)]
        end

        subgraph priv["Subredes PRIVADAS (route table SIN ruta a internet)"]
            direction TB
            subgraph a["AZ us-east-1a"]
                SA["subnet privada<br/>staging 172.31.240.0/24<br/>prod 172.31.242.0/24"]
            end
            subgraph b["AZ us-east-1b"]
                SB["subnet privada<br/>staging 172.31.241.0/24<br/>prod 172.31.243.0/24"]
            end
            TASKS[Tareas ECS Fargate<br/>consumer · exporter · prometheus · grafana]
            IFE{{"Interface endpoints<br/>ECR (api + dkr) · Logs · SQS<br/>private DNS a nivel VPC"}}
        end

        GWE{{Gateway endpoints<br/>S3 · DynamoDB<br/>en la route table privada}}
    end

    ALB -->|forward :3000| TASKS
    SA --- TASKS
    SB --- TASKS
    TASKS -.HTTPS interno.-> IFE
    TASKS -.ruta de la subnet.-> GWE
```

> Nota: staging y prod **comparten** la VPC default, por eso usan CIDRs distintos y los **interface
> endpoints se crean una vez (staging) y prod los reusa** (su private DNS es a nivel de toda la VPC).

### Lo importante de la red y la seguridad

- Las **Lambdas** y la **API Gateway** no están en la VPC (son "serverless", no manejás servidores).
- Los 4 contenedores corren en **ECS Fargate** dentro de la VPC, en **subredes privadas SIN IP
  pública**. Para hablar con los servicios de AWS (ECR, Logs, SQS, DynamoDB, S3) **no salen a
  internet**: usan **VPC Endpoints** (red interna de AWS). Esta es la buena práctica.
- **Grafana se expone por un ALB público** (subredes públicas) que reenvía al contenedor privado.
  Da una **URL estable** y pide usuario y contraseña. Prometheus y el exporter **no** son
  alcanzables desde internet (solo se ven por dentro de la VPC).

| Servicio            | Puerto | Quién puede entrar                                                       |
| ------------------- | ------ | ------------------------------------------------------------------------ |
| ALB → Grafana       | 80→3000 | Internet, **pero Grafana pide login** (anónimo apagado, pass en secreto) |
| Prometheus          | 9090   | Solo interno (no internet)                                               |
| metrics-exporter    | 9100   | Solo dentro de la VPC (no internet)                                      |
| f1-consumer         | —      | Nada entra (solo sale, por VPC endpoints)                                |
| RDS (base de datos) | 5432   | Internet con contraseña (las Lambdas están fuera de la VPC)              |

> 💰 **No puede explotar el costo:** la cuenta usa el plan de créditos gratis. Si algo se abusa, se
> gastan los créditos y AWS _pausa_ el acceso — nunca te llega una factura sorpresa a la tarjeta.

> ⚠️ **VPC compartida (deuda técnica conocida):** `staging` y `prod` viven en la **misma VPC default**.
> Por eso: (a) cada entorno usa **CIDRs de subred distintos** (staging `172.31.240/241`, prod
> `172.31.242/243`); y (b) los **interface endpoints** (ECR/Logs/SQS) tienen DNS privado a nivel de
> VPC, así que se crean **una sola vez en staging** y **prod los reusa**. Consecuencia: prod depende
> de staging para ese DNS (al apagar, apagar prod antes que staging). **Mejora correcta a futuro:**
> una **VPC dedicada por entorno**, así cada uno tiene sus propias subredes y endpoints sin compartir.

---

## 3. Tabla rápida de componentes

| Para qué           | Componente                     | Detalle                                                             |
| ------------------ | ------------------------------ | ------------------------------------------------------------------- |
| Puerta de entrada  | API Gateway (HTTP)             | Rutas `/ingest`, `/sessions`, `/drivers`, `/start-simulation`, etc. |
| Lógica por eventos | 8 Lambdas (Python)             | Ingesta, lecturas y arranque de simulación                          |
| Eventos internos   | EventBridge                    | Encadena `ingest_worker` y `save_session`                           |
| Procesos largos    | f1-consumer (Fargate)          | Cola SQS → métricas en DynamoDB                                     |
| Procesos largos    | metrics-exporter (Fargate)     | DynamoDB → métricas Prometheus, lleva el reloj                      |
| Monitoreo          | Prometheus + Grafana (Fargate) | Recolecta y dibuja los tableros                                     |
| Balanceador        | ALB (público)                  | Expone Grafana (privado) con URL estable                            |
| Red interna        | VPC Endpoints                  | S3/DynamoDB (gateway) + ECR/Logs/SQS (interface), sin salir a internet |
| Datos crudos       | S3                             | Lo que baja de OpenF1                                               |
| Base de datos      | RDS PostgreSQL                 | Eventos de la sesión (`session_events`)                             |
| Métricas           | DynamoDB                       | Una tabla, expira sola (TTL)                                        |
| Mensajería         | SQS + DLQ                      | Un mensaje por bloque; reintenta 3 veces                            |
| Imágenes           | ECR                            | 4 repos de contenedores                                             |
| Logs               | CloudWatch                     | Logs de Lambdas y contenedores                                      |

---

## 4. Interruptores (para prender/apagar y cuidar el costo)

| Variable            | Por defecto | Qué hace                                               |
| ------------------- | ----------- | ------------------------------------------------------ |
| `enable_ecs`        | `false`     | Crea el cluster +`f1-consumer` y `metrics-exporter`    |
| `enable_monitoring` | `false`     | Crea Prometheus + Grafana (necesita `enable_ecs=true`) |

Se configuran por entorno en `terraform/environments/<entorno>.tfvars`. Las imágenes se suben a ECR
en cada despliegue igual, así que prender un interruptor nunca falla por falta de imagen.

---

## 5. Cómo probarlo

```bash
API="https://<id-api>.execute-api.us-east-1.amazonaws.com"   # uno por entorno
curl "$API/ingest?session_key=9158"                          # async, ~30-60s la 1ra vez
curl -X POST "$API/start-simulation" -H 'content-type: application/json' \
     -d '{"session_id":"9158","simulation_duration_seconds":300}'
# después abrí Grafana, tablero "RaceTrack — F1 Telemetry", y elegí la simulación más nueva
```

Para ver las IPs actuales de Grafana/Prometheus (cambian al reiniciar la tarea):

```bash
cd project && ./scripts/monitoring_ips.sh            # staging
cd project && ENV=prod ./scripts/monitoring_ips.sh   # prod
```

---

## 6. Detalle de componentes (qué hace cada uno y con quién habla)

### Lambdas (8) — qué hace y con quién habla

| Lambda | Disparador | Hace | Conecta con |
| --- | --- | --- | --- |
| **ingest_session** | `GET /ingest` | Recibe el pedido, responde 202 y emite evento | → EventBridge (`IngestRequested`) |
| **ingest_worker** | EventBridge `IngestRequested` | Baja la sesión de OpenF1, decima telemetría a ~1 Hz, guarda crudo; emite evento | OpenF1 → **S3** → EventBridge (`SessionIngested`) |
| **save_session** | EventBridge `SessionIngested` | Lee el crudo, aplana 8 datasets y los inserta | **S3** → **RDS** |
| **list_session** | `GET /sessions` | Lista sesiones | **RDS** (lee) |
| **list_drivers** | `GET /drivers` | Lista pilotos de una sesión | **RDS** (lee) |
| **driver_summary** | `GET /driver-summary` | Resumen de un piloto | **RDS** (lee) |
| **driver_laps** | `GET /driver-laps` | Vueltas de un piloto | **RDS** (lee) |
| **start_simulation** | `POST /start-simulation` | Lee la sesión, la corta en bloques de 10 s de carrera y publica **1 mensaje por bloque** | **RDS** (lee) → **SQS** |

> Todas las Lambdas corren **fuera de la VPC**. Entran por **API Gateway** (salvo las 2 disparadas por EventBridge).

### ECS Fargate (4 contenedores, en subredes privadas)

| Servicio | Hace | Conecta con |
| --- | --- | --- |
| **f1-consumer** | Lee la cola, calcula métricas por piloto de cada bloque | **SQS** → **DynamoDB** |
| **metrics-exporter** | Lee las métricas y las sirve como gauges Prometheus (`:9100`), maneja el "reloj" de la simulación | **DynamoDB** → expone `/metrics` |
| **Prometheus** | Hace scrape del exporter (`:9090`) | ← metrics-exporter |
| **Grafana** | Consulta Prometheus y dibuja el dashboard (`:3000`, vía ALB) | ← Prometheus |

### SQS

Cola **`simulation-events`**: un mensaje por bloque de 10 s. **Productor:** `start_simulation`.
**Consumidor:** `f1-consumer`. Si un mensaje falla 3 veces → va a la **DLQ** (cola de descarte).

### Qué se guarda en cada store

- **S3** → los **payloads crudos** que baja de OpenF1 (telemetría decimada a ~1 Hz). Insumo intermedio.
- **RDS (PostgreSQL)** → tabla **`session_events`**: los eventos de la sesión ya aplanados/ordenados
  (lo que leen las APIs y `start_simulation`).
- **DynamoDB** → **métricas por bloque de la simulación** (tabla única: `PK=SIM#<id>`,
  `SK=META` o `BUCKET#<n>`, con TTL). Lo que escribe el consumer y lee el exporter.

**En una línea:** OpenF1 → (ingest) S3 → (save) RDS → (simulación) SQS → (consumer) DynamoDB →
(exporter → Prometheus → Grafana) dashboard.
