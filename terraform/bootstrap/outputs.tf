output "state_bucket_name" {
  value       = aws_s3_bucket.tf_state.id
  description = "Pass this value as TF_STATE_BUCKET in CI secrets"
}

output "lock_table_name" {
  value       = aws_dynamodb_table.tf_locks.name
  description = "Pass this value as TF_LOCK_TABLE in CI secrets (or hardcode in backend.tf)"
}
