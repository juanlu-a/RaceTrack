resource "aws_iam_role" "lambda_exec" {
  name = "${local.prefix}-lambda-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = local.common_tags
}

# CloudWatch Logs: required for all Lambda functions
resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ingest_session: write to S3 + put EventBridge events
resource "aws_iam_role_policy" "ingest_session" {
  name = "${local.prefix}-ingest-session"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:HeadObject", "s3:CreateBucket"]
        Resource = [
          aws_s3_bucket.sessions.arn,
          "${aws_s3_bucket.sessions.arn}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "events:PutEvents"
        Resource = "*"
      }
    ]
  })
}

# save_session: read from S3
resource "aws_iam_role_policy" "save_session" {
  name = "${local.prefix}-save-session"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:GetObject"]
      Resource = "${aws_s3_bucket.sessions.arn}/*"
    }]
  })
}

# start_simulation: publish bucket messages to the simulation SQS queue
resource "aws_iam_role_policy" "start_simulation" {
  name = "${local.prefix}-start-simulation"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sqs:SendMessage", "sqs:SendMessageBatch"]
      Resource = aws_sqs_queue.simulation.arn
    }]
  })
}

# ── ECS roles (f1-consumer + metrics-exporter) ───────────────────────────────

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: pull from ECR + write container logs to CloudWatch.
resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.prefix}-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Consumer task role: read/delete SQS bucket messages, write metrics to DynamoDB.
resource "aws_iam_role" "ecs_consumer_task" {
  name               = "${local.prefix}-ecs-consumer-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "ecs_consumer_task" {
  name = "${local.prefix}-ecs-consumer-task"
  role = aws_iam_role.ecs_consumer_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = aws_sqs_queue.simulation.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = aws_dynamodb_table.simulation_metrics.arn
      }
    ]
  })
}

# Exporter task role: read simulation metrics from DynamoDB.
resource "aws_iam_role" "ecs_exporter_task" {
  name               = "${local.prefix}-ecs-exporter-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy" "ecs_exporter_task" {
  name = "${local.prefix}-ecs-exporter-task"
  role = aws_iam_role.ecs_exporter_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:Query", "dynamodb:GetItem", "dynamodb:Scan"]
      Resource = aws_dynamodb_table.simulation_metrics.arn
    }]
  })
}
