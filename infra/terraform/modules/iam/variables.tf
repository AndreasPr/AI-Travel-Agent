variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "region" {
  description = "Operator-selected AWS region."
  type        = string
}

variable "account_id" {
  description = "Placeholder input only; never commit an actual account identifier."
  type        = string
}

variable "kms_key_arn" {
  description = "Existing customer-managed KMS key ARN with required service policies."
  type        = string
}

variable "log_group_arns" {
  description = "Exact log group ARNs keyed by api and web."
  type        = map(string)
}

variable "api_secret_arns" {
  description = "Only the API runtime secret entry ARNs."
  type        = list(string)
}
