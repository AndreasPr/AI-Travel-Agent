output "arns" {
  description = "Exact log group ARNs."
  value       = { for key, group in aws_cloudwatch_log_group.service : key => group.arn }
}
output "names" {
  description = "Log group names used by awslogs."
  value       = { for key, group in aws_cloudwatch_log_group.service : key => group.name }
}
