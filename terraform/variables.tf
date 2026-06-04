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

variable "db_host" {
  type        = string
  description = "PostgreSQL host (RDS endpoint or hostname)"
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
