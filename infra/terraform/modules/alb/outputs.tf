output "target_group_arns" {
  description = "Service target groups."
  value       = { for key, group in aws_lb_target_group.service : key => group.arn }
}
output "dns_name" {
  description = "ALB DNS name."
  value       = aws_lb.this.dns_name
}

output "security_group_id" {
  description = "Security group for the attached service."
  value       = aws_security_group.alb.id
}
