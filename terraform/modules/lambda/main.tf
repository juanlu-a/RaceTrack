terraform {
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.0" }
  }
}

# Minimal placeholder zip used on the FIRST terraform apply.
# The CI deploy job (aws lambda update-function-code) owns subsequent code updates.
# lifecycle.ignore_changes prevents Terraform from reverting CI-deployed code.
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/.placeholder_${var.function_name}.zip"
  source {
    content  = "def handler(e, c): return {'statusCode': 200, 'body': 'placeholder'}"
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = var.role_arn
  handler          = "handler.handler"
  runtime          = var.runtime
  timeout          = var.timeout
  memory_size      = var.memory_size
  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }

  # Terraform manages configuration (IAM, env vars, triggers).
  # Code is deployed separately via `aws lambda update-function-code` in CI.
  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}
