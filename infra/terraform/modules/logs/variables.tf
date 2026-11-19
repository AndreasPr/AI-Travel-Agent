variable "name" {
  description = "Resource name prefix; not an account identifier."
  type        = string
  default     = "travel-reference"
}

variable "kms_key_arn" {
  description = "Existing customer-managed KMS key ARN with required service policies."
  type        = string
}
