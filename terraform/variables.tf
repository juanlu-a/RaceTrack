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
