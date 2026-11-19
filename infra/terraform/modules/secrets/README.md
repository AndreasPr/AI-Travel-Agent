# Secrets module

validated, not deployed

Creates entries only, with KMS encryption and 30-day recovery. No secret version/value is created. Runtime values, least-privileged database user and safe rotation workflows require separate provisioning. Automatic rotation is not falsely configured against empty entries; Checkov findings remain unsuppressed.

Inputs and outputs are documented in variables.tf and outputs.tf.
