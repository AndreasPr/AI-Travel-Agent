# Iam module

validated, not deployed

Application task roles have no AWS API policies. Execution roles write only their own service streams; API execution alone can read the two exact secret ARNs and decrypt their KMS key via Secrets Manager with a matching encryption context. No wildcard actions or standalone wildcard resources. The only suffix wildcard and Checkov skip are documented in ../../../../docs/security-exceptions.md. Public images avoid the ECR GetAuthorizationToken standalone-wildcard requirement.

Inputs and outputs are documented in variables.tf and outputs.tf.
