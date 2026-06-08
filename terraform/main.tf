terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
  required_version = ">= 1.7"
}

provider "aws" {
  region = var.aws_region
}

# ── Lambda functions ──────────────────────────────────────────────────────────

module "ingest_session" {
  source = "./modules/lambda"

  function_name      = local.fn.ingest_session
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = {
    S3_BUCKET_NAME  = aws_s3_bucket.sessions.id
    S3_ENDPOINT     = ""
    EVENTS_ENDPOINT = ""
  }
}

module "save_session" {
  source = "./modules/lambda"

  function_name      = local.fn.save_session
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = merge(local.db_env_vars, {
    S3_ENDPOINT = ""
  })
}

module "list_session" {
  source = "./modules/lambda"

  function_name      = local.fn.list_session
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = local.db_env_vars
}

module "list_drivers" {
  source = "./modules/lambda"

  function_name      = local.fn.list_drivers
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = local.db_env_vars
}

module "driver_summary" {
  source = "./modules/lambda"

  function_name      = local.fn.driver_summary
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = local.db_env_vars
}

module "driver_laps" {
  source = "./modules/lambda"

  function_name      = local.fn.driver_laps
  role_arn           = aws_iam_role.lambda_exec.arn
  runtime            = var.lambda_runtime
  timeout            = var.lambda_timeout
  memory_size        = var.lambda_memory_size
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  environment_variables = local.db_env_vars
}

# ── API Gateway ───────────────────────────────────────────────────────────────

module "api_gateway" {
  source = "./modules/api_gateway"

  api_name           = "${local.prefix}-api"
  log_retention_days = var.log_retention_days
  tags               = local.common_tags

  routes = {
    "GET /ingest" = {
      invoke_arn    = module.ingest_session.invoke_arn
      function_name = module.ingest_session.function_name
    }
    "GET /sessions" = {
      invoke_arn    = module.list_session.invoke_arn
      function_name = module.list_session.function_name
    }
    "GET /drivers" = {
      invoke_arn    = module.list_drivers.invoke_arn
      function_name = module.list_drivers.function_name
    }
    "GET /driver-summary" = {
      invoke_arn    = module.driver_summary.invoke_arn
      function_name = module.driver_summary.function_name
    }
    "GET /driver-laps" = {
      invoke_arn    = module.driver_laps.invoke_arn
      function_name = module.driver_laps.function_name
    }
  }
}

# ── EventBridge ───────────────────────────────────────────────────────────────

module "eventbridge" {
  source = "./modules/eventbridge"

  rule_name            = "${local.prefix}-session-ingested"
  event_source         = "racetrack"
  detail_type          = "SessionIngested"
  target_function_arn  = module.save_session.function_arn
  target_function_name = module.save_session.function_name
  tags                 = local.common_tags
}
