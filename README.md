# RaceTrack

Pipeline de telemetría de Fórmula 1 en AWS: ingesta una sesión real de la API pública
[OpenF1](https://openf1.org), la guarda, la **reproduce como una simulación acelerada**, calcula
métricas por piloto y las muestra en vivo en **Grafana**. Desplegado en dos entornos (`staging` y
`prod`) con Terraform + GitHub Actions.

## 🔑 Grafana (URL estable vía ALB)

| Ambiente | URL | Usuario | Contraseña |
| --- | --- | --- | --- |
| **Staging** | http://racetrack-staging-grafana-alb-688930253.us-east-1.elb.amazonaws.com | `admin` | `TO0ZGW8RjQmSI5bxwPha5R` |
| **Producción** | http://racetrack-prod-grafana-alb-1692103895.us-east-1.elb.amazonaws.com | `admin` | `TO0ZGW8RjQmSI5bxwPha5R` |

Dashboard: **RaceTrack — F1 Telemetry**.

## 🌐 API de la app

| Ambiente | Base URL |
| --- | --- |
| **Staging** | `https://15foua88jk.execute-api.us-east-1.amazonaws.com` |
| **Producción** | `https://gzp7twnqsg.execute-api.us-east-1.amazonaws.com` |

## ▶️ Lanzar una nueva simulación

> Se lanza **desde la API** (no desde Grafana). Grafana solo la **muestra**.

**Staging:**
```bash
curl -X POST "https://15foua88jk.execute-api.us-east-1.amazonaws.com/start-simulation" \
     -H 'content-type: application/json' \
     -d '{"session_id":"9158","simulation_duration_seconds":300}'
```

**Producción:**
```bash
curl -X POST "https://gzp7twnqsg.execute-api.us-east-1.amazonaws.com/start-simulation" \
     -H 'content-type: application/json' \
     -d '{"session_id":"9158","simulation_duration_seconds":300}'
```

**Después, para verla:**
1. La respuesta trae un **`simulation_id`** → copialo.
2. Abrí el **Grafana de ese ambiente** → dashboard **RaceTrack — F1 Telemetry**.
3. Dropdown **Simulation** (arriba izq.) → elegí ese `simulation_id`.
4. Arriba der.: rango **Last 15 minutes** + auto-refresh **5s** (encendido).
5. Esperá ~30s y mirá avanzar los paneles (~5 min). Para repetir: relanzá el `curl` y elegí el nuevo id.

> `simulation_duration_seconds` = cuánto dura la reproducción (300 = 5 min).
> Si elegís una simulación vieja en el dropdown → "No data": elegí siempre la más reciente.

## 🏗️ Qué demuestra el sistema

- **Pipeline event-driven:** API Gateway → Lambdas → EventBridge → S3 → RDS.
- **Mensajería + procesamiento:** RDS → SQS → f1-consumer → DynamoDB (en **subredes privadas**).
- **Observabilidad:** DynamoDB → metrics-exporter → Prometheus → Grafana (por **ALB**, todo **sin IP pública**).

Detalle de arquitectura: ver [`docs/ARQUITECTURA.md`](./docs/ARQUITECTURA.md).

## ⚠️ Notas

- **Costo:** plan de créditos gratis (~$130) — no puede generar factura sorpresa (si se agotan, AWS
  pausa el acceso, no cobra tarjeta).
- **VPC compartida:** staging y prod comparten la VPC default → cada entorno usa CIDRs de subred
  distintos y los **interface endpoints** (ECR/Logs/SQS) se crean una sola vez en staging y prod los
  reusa. Consecuencia: **al apagar, apagar prod antes que staging**. Mejora "de libro": una VPC
  dedicada por entorno.
- **Apagar para no gastar créditos:** poner `enable_ecs`, `enable_monitoring` (y en prod
  `create_interface_endpoints`) en `false` en `terraform/environments/<env>.tfvars` y desplegar.
