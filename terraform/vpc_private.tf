# ── Subredes privadas + VPC Endpoints (buenas prácticas) ─────────────────────
# Las tareas ECS corren en estas subredes privadas SIN IP pública. Para alcanzar
# los servicios de AWS NO usan internet/NAT, sino VPC Endpoints (red interna):
#   - Gateway (gratis):  S3 (requerido para que ECR baje las capas) + DynamoDB
#   - Interface (~$7/mes): ECR api/dkr, CloudWatch Logs, SQS
# Todo gated en var.enable_ecs, así se crea/destruye junto con el cluster.

resource "aws_subnet" "private" {
  count             = var.enable_ecs ? length(var.private_subnet_cidrs) : 0
  vpc_id            = data.aws_vpc.default.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.private_subnet_azs[count.index]

  map_public_ip_on_launch = false

  tags = merge(local.common_tags, { Name = "${local.prefix}-private-${count.index}" })
}

# Route table privada: solo ruta local (sin 0.0.0.0/0 -> sin salida a internet).
resource "aws_route_table" "private" {
  count  = var.enable_ecs ? 1 : 0
  vpc_id = data.aws_vpc.default.id
  tags   = merge(local.common_tags, { Name = "${local.prefix}-private-rt" })
}

resource "aws_route_table_association" "private" {
  count          = var.enable_ecs ? length(var.private_subnet_cidrs) : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

# ── Gateway endpoints (gratis) ───────────────────────────────────────────────
resource "aws_vpc_endpoint" "s3" {
  count             = var.enable_ecs ? 1 : 0
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private[0].id]
  tags              = merge(local.common_tags, { Name = "${local.prefix}-vpce-s3" })
}

resource "aws_vpc_endpoint" "dynamodb" {
  count             = var.enable_ecs ? 1 : 0
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private[0].id]
  tags              = merge(local.common_tags, { Name = "${local.prefix}-vpce-dynamodb" })
}

# ── Security group para los Interface endpoints (HTTPS desde la VPC) ─────────
resource "aws_security_group" "vpce" {
  count       = var.enable_ecs ? 1 : 0
  name        = "${local.prefix}-vpce-sg"
  description = "HTTPS to interface VPC endpoints from inside the VPC"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTPS from within the VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

# ── Interface endpoints (PrivateLink) ────────────────────────────────────────
# ECR (api + dkr) para bajar imágenes, Logs para awslogs, SQS para el consumer.
# private_dns_enabled hace que los nombres DNS de AWS resuelvan a estos endpoints.
locals {
  interface_endpoints = var.enable_ecs ? toset([
    "ecr.api",
    "ecr.dkr",
    "logs",
    "sqs",
  ]) : toset([])
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = local.interface_endpoints
  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpce[0].id]
  private_dns_enabled = true

  tags = merge(local.common_tags, { Name = "${local.prefix}-vpce-${each.value}" })
}
