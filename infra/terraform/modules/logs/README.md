# Logs module

validated, not deployed

Creates one encrypted CloudWatch group per service with 365-day retention. skip_destroy retains groups if removed from Terraform. The existing KMS key must permit the CloudWatch service to use it; that external key policy is not provisioned or verified here.

Inputs and outputs are documented in variables.tf and outputs.tf.
