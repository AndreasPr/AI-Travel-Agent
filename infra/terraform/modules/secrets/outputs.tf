output "arns" {
  description = "Secret entry ARNs only; no secret values."
  value       = { for key, secret in aws_secretsmanager_secret.entry : key => secret.arn }
}
