output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}
output "public_subnet_ids" {
  description = "Two public subnet IDs; only for ALB and optional NAT."
  value       = [for subnet in aws_subnet.public : subnet.id]
}
output "private_subnet_ids" {
  description = "Two private subnet IDs for RDS and Fargate."
  value       = [for subnet in aws_subnet.private : subnet.id]
}
