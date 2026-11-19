variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "region" {
  description = "Operator-selected AWS region."
  type        = string
}

variable "images" {
  description = "Public registry image references pinned to immutable digests; keys api and web."
  type        = map(string)
}

variable "frontend_origin" {
  description = "Exact HTTPS frontend origin for API CORS; not a credential."
  type        = string
}

variable "desired_count" {
  description = "Task count; zero keeps this undeployed reference fail-closed."
  type        = number
  default     = 0
}

variable "private_subnet_ids" {
  description = "Private Fargate subnet IDs."
  type        = list(string)
}

variable "execution_role_arns" {
  description = "Per-service execution role ARNs."
  type        = map(string)
}

variable "task_role_arns" {
  description = "Per-service task role ARNs."
  type        = map(string)
}

variable "log_group_names" {
  description = "Per-service CloudWatch group names."
  type        = map(string)
}

variable "target_group_arns" {
  description = "Per-service ALB target group ARNs."
  type        = map(string)
}

variable "api_secret_arns" {
  description = "API runtime secret entry ARNs."
  type        = map(string)
}

variable "vpc_id" {
  description = "Application VPC ID."
  type        = string
}

variable "alb_security_group_id" {
  description = "ALB security group only."
  type        = string
}

variable "egress_cidrs" {
  description = "Approved external HTTPS destinations."
  type        = set(string)
}
