variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name)) && !endswith(var.name, "-")
    error_message = "Use a short lower-case resource prefix without a trailing hyphen."
  }
}

variable "region" {
  description = "Operator-selected AWS region."
  type        = string
}

variable "account_id" {
  description = "Placeholder input only; never commit an actual account identifier."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Account ID must be supplied outside git; examples intentionally contain placeholders."
  }
}

variable "availability_zones" {
  description = "Exactly two distinct AZs in the selected region."
  type        = list(string)
  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2
    error_message = "Supply exactly two distinct availability zones."
  }
}

variable "vpc_cidr" {
  description = "Operator-supplied IPv4 CIDR; no real network addresses in examples."
  type        = string
  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 4, 3))
    error_message = "Supply a valid IPv4 VPC CIDR with space for four subnets."
  }
}

variable "default_route_cidr" {
  description = "IPv4 default route destination supplied externally."
  type        = string
  validation {
    condition     = can(cidrnetmask(var.default_route_cidr)) && endswith(var.default_route_cidr, "/0")
    error_message = "Supply the IPv4 default-route destination outside git."
  }
}

variable "client_cidrs" {
  description = "Approved ALB client IPv4 CIDRs; empty denies all inbound traffic."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for cidr in var.client_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")])
    error_message = "Only explicit IPv4 client ranges are permitted; unrestricted ingress is forbidden."
  }
}

variable "egress_cidrs" {
  description = "Approved external HTTPS destinations; empty denies task internet egress."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for cidr in var.egress_cidrs : can(cidrnetmask(cidr)) && !endswith(cidr, "/0")])
    error_message = "Only approved IPv4 HTTPS destinations are permitted; unrestricted egress is forbidden."
  }
}

variable "enable_nat" {
  description = "Optional NAT gateways; OFF by default."
  type        = bool
  default     = false
}

variable "kms_key_arn" {
  description = "Existing customer-managed KMS key ARN with required service policies."
  type        = string
  validation {
    condition     = startswith(var.kms_key_arn, "arn:") && !strcontains(var.kms_key_arn, "*") && !strcontains(var.kms_key_arn, "?")
    error_message = "Supply an exact existing ARN outside git; wildcards are forbidden."
  }
}

variable "flow_log_bucket_arn" {
  description = "Existing encrypted S3 bucket ARN for VPC flow logs; bucket policy managed externally."
  type        = string
  validation {
    condition     = startswith(var.flow_log_bucket_arn, "arn:") && !strcontains(var.flow_log_bucket_arn, "*") && !strcontains(var.flow_log_bucket_arn, "?")
    error_message = "Supply an exact existing ARN outside git; wildcards are forbidden."
  }
}

variable "alb_log_bucket_name" {
  description = "Existing private S3 bucket permitting ALB access-log delivery."
  type        = string
}

variable "certificate_arn" {
  description = "Existing ACM certificate ARN in this region."
  type        = string
  validation {
    condition     = startswith(var.certificate_arn, "arn:") && !strcontains(var.certificate_arn, "*") && !strcontains(var.certificate_arn, "?")
    error_message = "Supply an exact existing ARN outside git; wildcards are forbidden."
  }
}

variable "web_acl_arn" {
  description = "Existing regional WAFv2 web ACL ARN."
  type        = string
  validation {
    condition     = startswith(var.web_acl_arn, "arn:") && !strcontains(var.web_acl_arn, "*") && !strcontains(var.web_acl_arn, "?")
    error_message = "Supply an exact existing ARN outside git; wildcards are forbidden."
  }
}

variable "monitoring_role_arn" {
  description = "Existing RDS enhanced-monitoring role ARN; review its permissions separately."
  type        = string
  validation {
    condition     = startswith(var.monitoring_role_arn, "arn:") && !strcontains(var.monitoring_role_arn, "*") && !strcontains(var.monitoring_role_arn, "?")
    error_message = "Supply an exact existing ARN outside git; wildcards are forbidden."
  }
}

variable "postgres_version" {
  description = "Explicit supported RDS PostgreSQL engine minor version."
  type        = string
}

variable "postgres_parameter_family" {
  description = "Matching PostgreSQL parameter group family."
  type        = string
}

variable "images" {
  description = "Public registry image references pinned to immutable digests; keys api and web."
  type        = map(string)
  validation {
    condition     = toset(keys(var.images)) == toset(["api", "web"]) && alltrue([for image in values(var.images) : can(regex("@sha256:[a-f0-9]{64}$", image))])
    error_message = "Supply api and web public images pinned by SHA-256 digest."
  }
}

variable "frontend_origin" {
  description = "Exact HTTPS frontend origin for API CORS; not a credential."
  type        = string
  validation {
    condition     = startswith(var.frontend_origin, "https://") && !strcontains(var.frontend_origin, "*")
    error_message = "Supply an exact HTTPS origin, never a wildcard."
  }
}

variable "desired_count" {
  description = "Task count; zero keeps this undeployed reference fail-closed."
  type        = number
  default     = 0
  validation {
    condition     = var.desired_count >= 0 && floor(var.desired_count) == var.desired_count
    error_message = "Task count must be a non-negative integer."
  }
}
