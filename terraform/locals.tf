locals {
  prefix = "racetrack-${var.env}"

  common_tags = {
    Project     = "RaceTrack"
    Environment = var.env
    ManagedBy   = "Terraform"
  }

  # S3 bucket name for raw session payloads (must be globally unique)
  sessions_bucket_name = "${local.prefix}-sessions"

  # Lambda function names follow the pattern: racetrack-<env>-<function>
  fn = {
    ingest_session   = "${local.prefix}-ingest-session"
    ingest_worker    = "${local.prefix}-ingest-worker"
    save_session     = "${local.prefix}-save-session"
    list_session     = "${local.prefix}-list-session"
    list_drivers     = "${local.prefix}-list-drivers"
    driver_summary   = "${local.prefix}-driver-summary"
    driver_laps      = "${local.prefix}-driver-laps"
    start_simulation = "${local.prefix}-start-simulation"
  }

  # DynamoDB single table holding per-bucket simulation metrics
  metrics_table_name = "${local.prefix}-simulation-metrics"

  # ECR repositories for the long-running container services
  ecr_repos = {
    f1_consumer      = "${local.prefix}-f1-consumer"
    metrics_exporter = "${local.prefix}-metrics-exporter"
  }

  db_env_vars = {
    DB_HOST     = aws_db_instance.racetrack.address
    DB_PORT     = tostring(var.db_port)
    DB_NAME     = var.db_name
    DB_USER     = var.db_user
    DB_PASSWORD = var.db_password
  }
}
