# ── ALB para Grafana ─────────────────────────────────────────────────────────
# Grafana corre en subredes privadas (sin IP pública). Este Application Load
# Balancer, público y en las subredes públicas de la VPC default, es la forma
# estándar de exponer un servicio privado — y da una URL estable (el DNS del ALB).
# Gated en var.enable_monitoring (se crea/destruye con el stack de monitoreo).

resource "aws_security_group" "alb" {
  count       = var.enable_monitoring ? 1 : 0
  name        = "${local.prefix}-alb-sg"
  description = "Public ALB fronting Grafana"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP from allowed clients"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.monitoring_ingress_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_lb" "grafana" {
  count              = var.enable_monitoring ? 1 : 0
  name               = "${local.prefix}-grafana-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb[0].id]
  # Public, one-per-AZ subnets only (default-for-az). Using all default subnets
  # would now also pick up the private subnets -> "multiple subnets in same AZ".
  subnets = data.aws_subnets.public.ids

  tags = local.common_tags
}

resource "aws_lb_target_group" "grafana" {
  count       = var.enable_monitoring ? 1 : 0
  name        = "${local.prefix}-grafana-tg"
  port        = var.grafana_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip" # Fargate awsvpc tasks register by IP

  health_check {
    path                = "/api/health"
    port                = "traffic-port"
    matcher             = "200"
    interval            = 30
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  tags = local.common_tags
}

resource "aws_lb_listener" "grafana" {
  count             = var.enable_monitoring ? 1 : 0
  load_balancer_arn = aws_lb.grafana[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana[0].arn
  }

  tags = local.common_tags
}
