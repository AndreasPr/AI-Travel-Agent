variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "kms_key_arn" {
  description = "Existing customer-managed KMS key ARN with required service policies."
  type        = string
}

variable "monitoring_role_arn" {
  description = "Existing RDS enhanced-monitoring role ARN; review its permissions separately."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs in two AZs; never public subnet IDs."
  type        = list(string)
}

variable "engine_version" {
  description = "Explicit RDS PostgreSQL engine minor version."
  type        = string
}

variable "parameter_family" {
  description = "Matching PostgreSQL parameter family."
  type        = string
}

variable "vpc_id" {
  description = "Application VPC ID."
  type        = string
}

variable "api_security_group_id" {
  description = "API task security group only."
  type        = string
}
