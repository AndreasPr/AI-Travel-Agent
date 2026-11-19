variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "certificate_arn" {
  description = "Existing ACM certificate ARN in this region."
  type        = string
}

variable "web_acl_arn" {
  description = "Existing regional WAFv2 web ACL ARN."
  type        = string
}

variable "vpc_id" {
  description = "Application VPC ID."
  type        = string
}

variable "public_subnet_ids" {
  description = "Two ALB subnets, not database subnets."
  type        = list(string)
}

variable "log_bucket_name" {
  description = "Existing ALB access-log bucket."
  type        = string
}

variable "client_cidrs" {
  description = "Approved client CIDRs; empty denies all inbound traffic."
  type        = set(string)
}
