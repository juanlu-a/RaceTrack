variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Name of the S3 bucket that stores Terraform state for all environments"
  default     = "racetrack-tf-state"
}

variable "lock_table_name" {
  type        = string
  description = "Name of the DynamoDB table used for Terraform state locking"
  default     = "racetrack-tf-locks"
}
