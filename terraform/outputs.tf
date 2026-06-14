output "api_endpoint" {
  value       = module.api_gateway.api_endpoint
  description = "Base URL — set as API_BASE_URL when running e2e tests"
}

output "sessions_bucket_name" {
  value = aws_s3_bucket.sessions.id
}

output "db_endpoint" {
  value       = aws_db_instance.racetrack.endpoint
  description = "RDS PostgreSQL endpoint (host:port)"
}

output "function_names" {
  value = {
    ingest_session   = module.ingest_session.function_name
    save_session     = module.save_session.function_name
    list_session     = module.list_session.function_name
    list_drivers     = module.list_drivers.function_name
    driver_summary   = module.driver_summary.function_name
    driver_laps      = module.driver_laps.function_name
    start_simulation = module.start_simulation.function_name
  }
}

output "simulation_queue_url" {
  value       = aws_sqs_queue.simulation.url
  description = "URL of the SQS queue that start_simulation publishes bucket messages to"
}
