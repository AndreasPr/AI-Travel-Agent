output "vpc_id" {
  description = "VPC identifier, only available after an explicitly authorized future deployment."
  value       = module.network.vpc_id
}
output "database_endpoint" {
  description = "Private RDS endpoint; not a connection string or password."
  value       = module.database.endpoint
}
output "alb_dns_name" {
  description = "ALB DNS name; a valid custom domain and certificate still need operator setup."
  value       = module.alb.dns_name
}
output "secret_arns" {
  description = "Empty secret entry ARNs, never secret values."
  value       = module.secrets.arns
}
output "cluster_arn" {
  description = "Fargate cluster ARN."
  value       = module.compute.cluster_arn
}
