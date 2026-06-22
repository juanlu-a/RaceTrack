variable "env" {
  type        = string
  description = "Deployment environment: 'staging' or 'prod'"
  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "env must be 'staging' or 'prod'"
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "db_port" {
  type    = number
  default = 5432
}

variable "db_name" {
  type    = string
  default = "racetrack"
}

variable "db_user" {
  type    = string
  default = "racetrack"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL password — injected via TF_VAR_db_password env var in CI, never in .tfvars"
}

variable "db_allowed_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to reach the RDS instance on db_port. Lambdas run outside a VPC with dynamic egress IPs, so this defaults to open."
  default     = ["0.0.0.0/0"]
}

# ── Subredes privadas para las tareas ECS ────────────────────────────────────

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDRs for the private subnets that host the ECS tasks (new blocks inside the default VPC 172.31.0.0/16, not overlapping the default subnets)."
  default     = ["172.31.240.0/24", "172.31.241.0/24"]
}

variable "private_subnet_azs" {
  type        = list(string)
  description = "Availability zones for the private subnets (must match the length of private_subnet_cidrs)."
  default     = ["us-east-1a", "us-east-1b"]
}

variable "create_interface_endpoints" {
  type        = bool
  description = "Create the interface VPC endpoints (ECR/Logs/SQS). Their private DNS is VPC-wide; since staging and prod share the default VPC, only ONE env should create them (staging=true) and the other reuses them (prod=false)."
  default     = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_allocated_storage" {
  type    = number
  default = 20
}

variable "db_engine_version" {
  type    = string
  default = "16"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = true
}

variable "db_deletion_protection" {
  type    = bool
  default = false
}

variable "lambda_timeout" {
  type    = number
  default = 60
}

variable "lambda_memory_size" {
  type    = number
  default = 256
}

variable "lambda_runtime" {
  type    = string
  default = "python3.9"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# ── ECS / containers (f1-consumer + metrics-exporter) ────────────────────────

variable "enable_ecs" {
  type        = bool
  description = "Create the ECS cluster + services. Keep false until the first container images are pushed to ECR, then flip to true."
  default     = false
}

variable "consumer_image_tag" {
  type    = string
  default = "latest"
}

variable "exporter_image_tag" {
  type    = string
  default = "latest"
}

variable "ecs_cpu" {
  type    = number
  default = 256
}

variable "ecs_memory" {
  type    = number
  default = 512
}

variable "metrics_port" {
  type        = number
  description = "Port the metrics-exporter serves Prometheus /metrics on"
  default     = 9100
}

variable "dynamodb_ttl_days" {
  type        = number
  description = "Days before a simulation's metrics items auto-expire via TTL"
  default     = 7
}

variable "ecr_keep_last_images" {
  type        = number
  description = "Number of most-recent images to retain per ECR repository"
  default     = 10
}

# ── Monitoring (Prometheus + Grafana on ECS) ─────────────────────────────────

variable "enable_monitoring" {
  type        = bool
  description = "Create the Prometheus + Grafana Fargate services. Requires enable_ecs=true (Prometheus scrapes the metrics-exporter via Service Connect). Keep false until the prometheus/grafana images are pushed to ECR."
  default     = false
}

variable "prometheus_image_tag" {
  type    = string
  default = "latest"
}

variable "grafana_image_tag" {
  type    = string
  default = "latest"
}

variable "prometheus_port" {
  type        = number
  description = "Port Prometheus serves on"
  default     = 9090
}

variable "grafana_port" {
  type        = number
  description = "Port Grafana serves the UI on"
  default     = 3000
}

variable "monitoring_ingress_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to reach the Prometheus (prometheus_port) and Grafana (grafana_port) UIs"
  default     = ["0.0.0.0/0"]
}

variable "grafana_admin_password" {
  type        = string
  sensitive   = true
  description = "Grafana admin password — injected via TF_VAR_grafana_admin_password in CI"
  default     = "admin"
}
