# ── Monitoring: Prometheus + Grafana (Fargate) ───────────────────────────────
# Gated on var.enable_monitoring (which requires var.enable_ecs, since Prometheus
# scrapes the metrics-exporter). Services talk to each other over ECS Service
# Connect using stable names — Prometheus scrapes "metrics-exporter:<port>" and
# Grafana queries "prometheus:<port>". Both run in the default VPC's public
# subnets with assign_public_ip=true (no NAT); reach the UIs at each task's
# public IP (Grafana on grafana_port, Prometheus on prometheus_port). There is
# no load balancer or persistent volume — this is a lightweight, default-off
# stack; the verified path is the local docker-compose monitoring stack.

check "monitoring_requires_ecs" {
  assert {
    condition     = !var.enable_monitoring || var.enable_ecs
    error_message = "enable_monitoring=true requires enable_ecs=true (Prometheus scrapes the metrics-exporter service)."
  }
}

resource "aws_service_discovery_http_namespace" "monitoring" {
  count       = var.enable_monitoring ? 1 : 0
  name        = local.prefix
  description = "Service Connect namespace for the RaceTrack monitoring stack"
  tags        = local.common_tags
}

resource "aws_cloudwatch_log_group" "prometheus" {
  count             = var.enable_monitoring ? 1 : 0
  name              = "/ecs/${local.prefix}/prometheus"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

resource "aws_cloudwatch_log_group" "grafana" {
  count             = var.enable_monitoring ? 1 : 0
  name              = "/ecs/${local.prefix}/grafana"
  retention_in_days = var.log_retention_days
  tags              = local.common_tags
}

# One SG for both monitoring services. Only Grafana's UI is exposed publicly;
# Prometheus is NOT internet-reachable — Grafana queries it over the internal
# self-referential rule (Service Connect, same SG). This shrinks the public
# attack surface to just the password-protected Grafana UI.
resource "aws_security_group" "monitoring" {
  count       = var.enable_monitoring ? 1 : 0
  name        = "${local.prefix}-monitoring-sg"
  description = "Grafana UI (public) + internal Prometheus query/scrape traffic"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Grafana UI"
    from_port   = var.grafana_port
    to_port     = var.grafana_port
    protocol    = "tcp"
    cidr_blocks = var.monitoring_ingress_cidrs
  }

  ingress {
    description = "Internal Service Connect traffic between monitoring tasks (Grafana to Prometheus)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# ── Prometheus ───────────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "prometheus" {
  count                    = var.enable_monitoring ? 1 : 0
  family                   = "${local.prefix}-prometheus"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name      = "prometheus"
    image     = "${aws_ecr_repository.services["prometheus"].repository_url}:${var.prometheus_image_tag}"
    essential = true
    portMappings = [{
      name          = "http"
      containerPort = var.prometheus_port
      protocol      = "tcp"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.prometheus[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "prometheus"
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_ecs_service" "prometheus" {
  count           = var.enable_monitoring ? 1 : 0
  name            = "${local.prefix}-prometheus"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.prometheus[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.monitoring[0].id]
    assign_public_ip = true
  }

  # Advertise "prometheus:<port>" for Grafana, and act as a client so it can
  # reach "metrics-exporter:<port>".
  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.monitoring[0].arn
    service {
      port_name      = "http"
      discovery_name = "prometheus"
      client_alias {
        port     = var.prometheus_port
        dns_name = "prometheus"
      }
    }
  }

  tags = local.common_tags
}

# ── Grafana ──────────────────────────────────────────────────────────────────

resource "aws_ecs_task_definition" "grafana" {
  count                    = var.enable_monitoring ? 1 : 0
  family                   = "${local.prefix}-grafana"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.ecs_cpu
  memory                   = var.ecs_memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name      = "grafana"
    image     = "${aws_ecr_repository.services["grafana"].repository_url}:${var.grafana_image_tag}"
    essential = true
    portMappings = [{
      name          = "http"
      containerPort = var.grafana_port
      protocol      = "tcp"
    }]
    environment = [
      { name = "GF_SECURITY_ADMIN_PASSWORD", value = var.grafana_admin_password },
      { name = "GF_AUTH_ANONYMOUS_ENABLED", value = "false" },
      { name = "GF_SERVER_HTTP_PORT", value = tostring(var.grafana_port) },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.grafana[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "grafana"
      }
    }
  }])

  tags = local.common_tags
}

resource "aws_ecs_service" "grafana" {
  count           = var.enable_monitoring ? 1 : 0
  name            = "${local.prefix}-grafana"
  cluster         = aws_ecs_cluster.main[0].id
  task_definition = aws_ecs_task_definition.grafana[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.monitoring[0].id]
    assign_public_ip = true
  }

  # Client-only: lets Grafana reach "prometheus:<port>" over Service Connect.
  service_connect_configuration {
    enabled   = true
    namespace = aws_service_discovery_http_namespace.monitoring[0].arn
  }

  tags = local.common_tags
}
