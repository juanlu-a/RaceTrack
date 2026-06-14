# Staging environment variables
# db_password is NOT here — injected via TF_VAR_db_password GitHub Secret

env        = "staging"
aws_region = "us-east-1"

# DB host is provisioned by Terraform (aws_db_instance.racetrack) and wired
# into the Lambdas automatically — no manual endpoint needed.
db_port = 5432
db_name = "racetrack"
db_user = "racetrack"

# RDS sizing — free-tier friendly for staging
db_instance_class      = "db.t3.micro"
db_allocated_storage   = 20
db_engine_version      = "16"
db_multi_az            = false
db_skip_final_snapshot = true
db_deletion_protection = false

lambda_timeout     = 60
lambda_memory_size = 256
lambda_runtime     = "python3.9"
log_retention_days = 7
