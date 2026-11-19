output "task_role_arns" {
  description = "Task roles with no AWS API permissions."
  value       = { for key, role in aws_iam_role.task : key => role.arn }
}
output "execution_role_arns" {
  description = "Execution roles; API alone may retrieve its two secrets."
  value       = { for key, role in aws_iam_role.execution : key => role.arn }
  depends_on  = [aws_iam_role_policy.log_delivery, aws_iam_role_policy.api_secrets]
}
