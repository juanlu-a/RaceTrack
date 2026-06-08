terraform {
  backend "s3" {
    # Bucket and lock table created by terraform/bootstrap
    bucket         = "racetrack-tf-state"
    region         = "us-east-1"
    dynamodb_table = "racetrack-tf-locks"
    encrypt        = true
    # key is injected at init time:
    #   staging: terraform init -backend-config="key=staging/terraform.tfstate"
    #   prod:    terraform init -backend-config="key=prod/terraform.tfstate"
  }
}
