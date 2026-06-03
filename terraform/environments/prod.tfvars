# Production environment variables
# db_password is NOT here — injected via TF_VAR_db_password GitHub Secret

env        = "prod"
aws_region = "us-east-1"

# Replace with your production RDS endpoint after provisioning the database
db_host = "prod-db.REPLACE_ME.us-east-1.rds.amazonaws.com"
db_port = 5432
db_name = "racetrack"
db_user = "racetrack"

lambda_timeout     = 60
lambda_memory_size = 256
lambda_runtime     = "python3.9"
log_retention_days = 14
