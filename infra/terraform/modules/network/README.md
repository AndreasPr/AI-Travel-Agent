# Network module

validated, not deployed

NAT defaults to false. Public subnets have Internet-gateway routing but do not assign public addresses to instances. Private subnets have no internet route unless optional NAT is enabled. VPC endpoints are not created: Logs and Secrets Manager endpoints or an approved NAT path are future prerequisites; ECR also needs API/DKR and S3 connectivity. Flow logs use a caller-owned S3 destination whose encryption/delivery policy must be reviewed separately.

Inputs and outputs are documented in variables.tf and outputs.tf.
