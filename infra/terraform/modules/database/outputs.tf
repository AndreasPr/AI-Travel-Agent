output "endpoint" {
  description = "Private database endpoint; contains no password."
  value       = aws_db_instance.postgres.endpoint
}
output "arn" {
  description = "Database ARN."
  value       = aws_db_instance.postgres.arn
}

output "security_group_id" {
  description = "Security group for the attached service."
  value       = aws_security_group.database.id
}
