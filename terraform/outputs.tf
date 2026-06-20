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

output "metrics_table_name" {
  value       = aws_dynamodb_table.simulation_metrics.name
  description = "DynamoDB table holding per-bucket simulation metrics"
}

output "ecr_repository_urls" {
  value       = { for k, repo in aws_ecr_repository.services : k => repo.repository_url }
  description = "ECR repo URLs to push the container images to"
}

output "ecs_cluster_name" {
  value       = var.enable_ecs ? aws_ecs_cluster.main[0].name : null
  description = "ECS cluster name (null until enable_ecs=true)"
}

output "ecs_service_names" {
  value = var.enable_ecs ? {
    f1_consumer      = aws_ecs_service.f1_consumer[0].name
    metrics_exporter = aws_ecs_service.metrics_exporter[0].name
  } : null
  description = "ECS service names (null until enable_ecs=true)"
}

output "monitoring_service_names" {
  value = var.enable_monitoring ? {
    prometheus = aws_ecs_service.prometheus[0].name
    grafana    = aws_ecs_service.grafana[0].name
  } : null
  description = "Prometheus/Grafana ECS service names (null until enable_monitoring=true). Reach the UIs at each task's public IP — Grafana on grafana_port, Prometheus on prometheus_port."
}
