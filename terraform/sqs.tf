# ── SQS: race simulation events ───────────────────────────────────────────────
# start_simulation publishes one message per 10s race-time bucket here.
# Standard queue (not FIFO): ordering is approximated via per-message
# DelaySeconds; consumers should reorder by bucket_index in the message body.

resource "aws_sqs_queue" "simulation_dlq" {
  name = "${local.prefix}-simulation-events-dlq"
  tags = local.common_tags
}

resource "aws_sqs_queue" "simulation" {
  name = "${local.prefix}-simulation-events"

  # Move poison messages to the DLQ after 3 failed receives (protects a future
  # consumer; no consumer is implemented yet).
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.simulation_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}
