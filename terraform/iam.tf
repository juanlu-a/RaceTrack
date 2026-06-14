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
