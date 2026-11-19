variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "availability_zones" {
  description = "Exactly two distinct AZs in the selected region."
  type        = list(string)
}

variable "vpc_cidr" {
  description = "Operator-supplied IPv4 CIDR; no real network addresses in examples."
  type        = string
}

variable "default_route_cidr" {
  description = "IPv4 default route destination supplied externally."
  type        = string
}

variable "enable_nat" {
  description = "Optional NAT gateways; OFF by default."
  type        = bool
  default     = false
}

variable "flow_log_bucket_arn" {
  description = "Existing encrypted S3 bucket ARN for VPC flow logs; bucket policy managed externally."
  type        = string
}
