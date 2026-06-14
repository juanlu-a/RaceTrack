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
    ingest_session = "${local.prefix}-ingest-session"
    save_session   = "${local.prefix}-save-session"
    list_session   = "${local.prefix}-list-session"
    list_drivers   = "${local.prefix}-list-drivers"
    driver_summary = "${local.prefix}-driver-summary"
    driver_laps    = "${local.prefix}-driver-laps"
  }

  db_env_vars = {
    DB_HOST     = aws_db_instance.racetrack.address
    DB_PORT     = tostring(var.db_port)
    DB_NAME     = var.db_name
    DB_USER     = var.db_user
    DB_PASSWORD = var.db_password
  }
}
