# Synthetic Terraform policy tests

These minimal fixtures test CKV_AWS_17, not deployment or AWS behavior.
Run Checkov with `--check CKV_AWS_17` only on these fixtures: pass/ must exit 0,
fail/ must exit 1. The real infrastructure scan always runs all applicable checks.
No account, credentials, addresses, provider initialization, plan or apply is needed.
