output "cluster_arn" {
  description = "ECS cluster ARN."
  value       = aws_ecs_cluster.this.arn
}
output "service_names" {
  description = "Service names; desired count defaults to zero."
  value       = { api = aws_ecs_service.api.name, web = aws_ecs_service.web.name }
}

output "security_group_ids" {
  description = "Security group for the attached service."
  value       = local.security_group_ids
}
