# ── DynamoDB: per-bucket simulation metrics ──────────────────────────────────
# Single table written by the f1-consumer (one item per 10s bucket) and read by
# the metrics-exporter. On-demand billing (no idle cost), no GSI; the exporter
# reads a simulation in chronological order with a single Query on the padded
# BUCKET# sort key. Items auto-expire via the `ttl` attribute.

resource "aws_dynamodb_table" "simulation_metrics" {
  name         = local.metrics_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = local.common_tags
}
