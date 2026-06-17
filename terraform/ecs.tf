# ── ECS: f1-consumer + metrics-exporter (Fargate) ────────────────────────────
# Gated on var.enable_ecs so the cluster/services are only created once the first
# images exist in ECR (otherwise tasks crash-loop pulling a missing tag). Both
# services run in the default VPC's (public) subnets with assign_public_ip=true:
# there is no NAT gateway, so a public IP is what lets tasks reach ECR/SQS/
# DynamoDB. The exporter additionally exposes metrics_port for scraping.

resource "aws_ecs_cluster" "main" {
  count = var.enable_ecs ? 1 : 0
  name  = "${local.prefix}-cluster"
  tags  = local.common_tags
}

resource "aws_cloudwatch_log_group" "f1_consumer" {
  count             = var.enable_ecs ? 1 : 0
  name              = "/ecs/${local.prefix}/f1-consumer"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "metrics_exporter" {
  count             = var.enable_ecs ? 1 : 0
  name              = "/ecs/${local.prefix}/metrics-exporter"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# Security group for the consumer: egress only (no inbound listeners).
resource "aws_security_group" "ecs_consumer" {
  count       = var.enable_ecs ? 1 : 0
  name        = "${local.prefix}-ecs-consumer-sg"
  description = "f1-consumer egress to SQS/DynamoDB/ECR"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# Security group for the exporter: allow scraping metrics_port + egress.
resource "aws_security_group" "ecs_exporter" {
  count       = var.enable_ecs ? 1 : 0
  name        = "${local.prefix}-ecs-exporter-sg"
  description = "metrics-exporter Prometheus scrape + egress"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Prometheus scrape"
    from_port   = var.metrics_port
    to_port     = var.metrics_port
    protocol    = "tcp"
    cidr_blocks = var.metrics_scrape_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "f1_consumer" {
  count                    = var.enable_ecs ? 1 : 0
  family                   = "${local.prefix}-f1-consumer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_consumer_task.arn

  container_definitions = jsonencode([{
    name      = "f1-consumer"
    image     = "${aws_ecr_repository.services["f1_consumer"].repository_url}:${var.consumer_image_tag}"
    essential = true
    environment = [
      { name = "SQS_QUEUE_URL", value = aws_sqs_queue.simulation.url },
      { name = "DYNAMODB_TABLE", value = aws_dynamodb_table.simulation_metrics.name },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "TTL_DAYS", value = tostring(var.dynamodb_ttl_days) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.f1_consumer[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "f1-consumer"
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_ecs_task_definition" "metrics_exporter" {
  count                    = var.enable_ecs ? 1 : 0
  family                   = "${local.prefix}-metrics-exporter"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_exporter_task.arn

  container_definitions = jsonencode([{
    name      = "metrics-exporter"
    image     = "${aws_ecr_repository.services["metrics_exporter"].repository_url}:${var.exporter_image_tag}"
    essential = true
    portMappings = [{
      containerPort = var.metrics_port
      protocol      = "tcp"
    }]
    environment = [
      { name = "DYNAMODB_TABLE", value = aws_dynamodb_table.simulation_metrics.name },
      { name = "AWS_DEFAULT_REGION", value = var.aws_region },
      { name = "METRICS_PORT", value = tostring(var.metrics_port) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.metrics_exporter[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "metrics-exporter"
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_ecs_service" "f1_consumer" {
  count           = var.enable_ecs ? 1 : 0
  name            = "${local.prefix}-f1-consumer"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.f1_consumer[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_consumer[0].id]
    assign_public_ip = true
  }

  tags = local.common_tags
}

resource "aws_ecs_service" "metrics_exporter" {
  count           = var.enable_ecs ? 1 : 0
  name            = "${local.prefix}-metrics-exporter"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.metrics_exporter[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs_exporter[0].id]
    assign_public_ip = true
  }

  tags = local.common_tags
}
