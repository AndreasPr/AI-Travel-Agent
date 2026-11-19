# Compute module

validated, not deployed

API and web use private subnets and separate security groups; no public task addresses. Image references are supplied externally; public images are required because no ECR wildcard authorization is granted. Desired count defaults to zero. APP_ENV is production; API secrets are references to empty entries, not values. No claim of runnable deployment is made until network, secret, cache/model and image prerequisites are satisfied.

Inputs and outputs are documented in variables.tf and outputs.tf.
