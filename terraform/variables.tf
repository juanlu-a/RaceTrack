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

variable "metrics_scrape_cidrs" {
  type        = list(string)
  description = "CIDR blocks allowed to scrape the metrics-exporter on metrics_port"
  default     = ["0.0.0.0/0"]
}
