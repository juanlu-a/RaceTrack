terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

resource "aws_cloudwatch_event_rule" "this" {
  name        = var.rule_name
  description = "Route ${var.event_source}/${var.detail_type} events to ${var.target_function_name}"

  event_pattern = jsonencode({
    source      = [var.event_source]
    "detail-type" = [var.detail_type]
  })

  tags = var.tags
}

resource "aws_cloudwatch_event_target" "this" {
  rule = aws_cloudwatch_event_rule.this.name
  arn  = var.target_function_arn
}

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.target_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.this.arn
}
