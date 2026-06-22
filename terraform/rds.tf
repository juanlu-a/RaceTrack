# PostgreSQL database backing the read/save Lambdas.
#
# The Lambdas run OUTSIDE a VPC (they need public internet egress for OpenF1,
# S3 and EventBridge), so the instance is publicly accessible and reached over
# its public endpoint. Access is gated by the security group below.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Only the original default subnets (one public subnet per AZ). We filter on
# default-for-az so this EXCLUDES the private subnets we create in vpc_private.tf
# (which live in the same shared default VPC). Used for the public ALB and the
# RDS subnet group — both need the original public, one-per-AZ subnets.
data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_db_subnet_group" "racetrack" {
  name       = "${local.prefix}-db-subnets"
  subnet_ids = data.aws_subnets.public.ids
  tags       = local.common_tags
}

resource "aws_security_group" "rds" {
  name        = "${local.prefix}-rds-sg"
  description = "Allow Postgres access to the RaceTrack RDS instance"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "PostgreSQL"
    from_port   = var.db_port
    to_port     = var.db_port
    protocol    = "tcp"
    cidr_blocks = var.db_allowed_cidrs
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = local.common_tags
}

resource "aws_db_instance" "racetrack" {
  identifier             = "${local.prefix}-db"
  engine                 = "postgres"
  engine_version         = var.db_engine_version
  instance_class         = var.db_instance_class
  allocated_storage      = var.db_allocated_storage
  storage_type           = "gp3"
  db_name                = var.db_name
  username               = var.db_user
  password               = var.db_password
  port                   = var.db_port
  db_subnet_group_name   = aws_db_subnet_group.racetrack.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = true
  multi_az               = var.db_multi_az
  skip_final_snapshot    = var.db_skip_final_snapshot
  deletion_protection    = var.db_deletion_protection
  apply_immediately      = true
  tags                   = local.common_tags
}
