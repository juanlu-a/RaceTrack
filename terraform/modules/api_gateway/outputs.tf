output "api_endpoint" {
  value       = aws_apigatewayv2_stage.default.invoke_url
  description = "Base URL of the deployed API Gateway (e.g. https://<id>.execute-api.<region>.amazonaws.com)"
}

output "api_id" {
  value = aws_apigatewayv2_api.this.id
}
