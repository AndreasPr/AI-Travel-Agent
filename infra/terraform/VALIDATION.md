# Validation record — 2026-11-19

validated, not deployed

Terraform syntax/schema validation passed. **Security validation did not pass:**
four Checkov findings remain blocking. This is not a deployment approval or a claim
that runtime connectivity, TLS, secret rotation or external-resource policies work.

## Commands and exact output

Tools: Terraform 1.5.7, AWS provider 6.42.0 (generated lockfile committed),
TFLint 0.65.0, Checkov 3.3.30 in a temporary Python 3.12 virtual environment.
No application dependencies were changed. The temporary environment was removed
after scanning. AWS environment variables were removed for provider initialization
and validation; no credentials, AWS data sources, remote state, plan or apply were used.
The first provider download stalled and was interrupted; the retry succeeded.

### terraform init -backend=false -input=false -no-color

Exit: 0. Terraform's generic output mentions plan; no plan was executed.

```text
Initializing modules...

Initializing provider plugins...
- Finding hashicorp/aws versions matching "6.42.0"...
- Installing hashicorp/aws v6.42.0...
- Installed hashicorp/aws v6.42.0 (signed by HashiCorp)

Terraform has created a lock file .terraform.lock.hcl to record the provider
selections it made above. Include this file in your version control repository
so that Terraform can guarantee to make the same selections by default when
you run "terraform init" in the future.

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
```

### terraform fmt -check -recursive -no-color

Exit: 0. No output.

### terraform validate -no-color

Exit: 0.

```text
Success! The configuration is valid.

```

### tflint --chdir=infra/terraform --recursive --config="$PWD/infra/terraform/.tflint.hcl"

Exit: 0. No output. Built-in recommended Terraform rules; no AWS plugin was installed.

### checkov -d infra/terraform --framework terraform --skip-download --download-external-modules false --compact --quiet

Exit: 1.

```text
terraform scan results:

Passed checks: 170, Failed checks: 4, Skipped checks: 2

Check: CKV_AWS_378: "Ensure AWS Load Balancer doesn't use HTTP protocol"
	FAILED for resource: module.alb.aws_lb_target_group.service["api"]
	File: /modules/alb/main.tf:16-27
Check: CKV2_AWS_76: "Ensure AWS ALB attached WAFv2 WebACL is configured with AMR for Log4j Vulnerability"
	FAILED for resource: module.alb.aws_lb.this
	File: /modules/alb/main.tf:1-15
Check: CKV2_AWS_57: "Ensure Secrets Manager secrets should have automatic rotation enabled"
	FAILED for resource: module.secrets.aws_secretsmanager_secret.entry["JWT_SECRET"]
	File: /modules/secrets/main.tf:2-8
Check: CKV2_AWS_57: "Ensure Secrets Manager secrets should have automatic rotation enabled"
	FAILED for resource: module.secrets.aws_secretsmanager_secret.entry["DATABASE_URL"]
	File: /modules/secrets/main.tf:2-8

```

The JSON scan also reported zero parsing errors and 53 resources. No severity is
invented for offline policies without severity metadata. CI fails every non-skipped
finding, including unscored findings; this is stricter than failing HIGH/CRITICAL only.

## Findings left open — no additional skips

| Check | Resource | Reason it remains open |
|---|---|---|
| CKV_AWS_378 | ALB API target group | Existing containers serve HTTP. ALB frontend TLS and HTTP redirect are configured, but backend transport is not TLS. Both service target groups use HTTP, even though this scan reports the API instance. Changing the setting to HTTPS without a TLS-serving container would be misleading and break health checks. Application/proxy TLS work is outside this reference. |
| CKV2_AWS_76 | ALB | An existing WAF ACL ARN is supplied, but its managed-rule contents cannot be established by offline validation. No claim is made that it includes Log4j protections. This remains a genuine unverified prerequisite, not an exception. |
| CKV2_AWS_57 | JWT_SECRET entry | Entry intentionally has no value/version. Safe application signing-key rotation is not implemented; no fictitious rotation Lambda or schedule is supplied. |
| CKV2_AWS_57 | DATABASE_URL entry | Entry intentionally has no value/version. A least-privileged application database user and its rotation workflow require separately authorized work. RDS's managed master secret is distinct and is not injected into the app. |

The only skip is CKV_AWS_355 on the log_delivery resource template, expanded into
API and web (two reported skips). See ../../docs/security-exceptions.md for the exact
statement, runtime task-ID rationale, scope and 2026-12-19 review date.
The Terraform security workflow is expected to fail until the four open findings
are resolved; there is no soft-fail or hidden baseline accepting them.

## Synthetic policy regression fixtures

These are scripted policy tests, not AWS measurements. Checkov was run with
`--framework terraform --skip-download --check CKV_AWS_17 --compact` separately on:

- `tests/terraform/private_database/pass`: exit 0, Passed checks: 1, Failed checks: 0, Skipped checks: 0.
- `tests/terraform/private_database/fail`: exit 1 (expected), Passed checks: 0, Failed checks: 1, Skipped checks: 0.

The real infrastructure scan runs all policies; the fixture-only check selection
is not used to exclude policies from production configuration scanning.

## Manual security review performed

- Root wiring sends only network.private_subnet_ids into RDS and Fargate; public
  subnet IDs go only to the ALB. Public-IP assignment is disabled for tasks/subnets;
  RDS publicly_accessible is false. Private default routes exist only with enabled NAT.
- NAT defaults false in root and network module. Default VPC security group has no
  ingress or egress. No default unrestricted CIDR is embedded or supplied.
- ALB ingress: approved client CIDRs only, TCP 80 redirect and TCP 443. Root input
  validations reject unrestricted CIDRs. Defaults deny all clients.
- Task ingress: ALB SG only, API 8080 / web 3000. ALB egress references those exact
  SGs/ports. Database ingress and matching API egress use exact SG references on
  TCP 5432; the web SG has no DB access. Optional external egress is approved CIDRs
  on TCP 443 only; default is empty. No SSH, RDP or all-protocol rules were added.
- No wildcard IAM action or standalone wildcard Resource occurs in an allow statement.
  The sole suffix wildcard is own-group, own-prefix log delivery with the two
  approved actions. Only API execution reads exact runtime-secret ARNs; KMS decrypt
  is exact-key, ViaService and SecretARN-context constrained. App task roles grant
  no AWS API actions. No broad managed execution policy or ECR auth grant is used.
- No secret versions, values or secret-value outputs. All example account IDs, ARNs,
  CIDRs and image digests are placeholders. No AWS data-source discovery is used.
- Reviewed CI: read-only repository permission, pinned Terraform/provider/scanner
  versions, local backend-disabled init, no credential action, no OIDC permission,
  no backend, plan or apply. Provider lockfile is tracked; cache/state/real tfvars
  are ignored. Checkov's temporary environment is removed even on scan failure.

## NOT run / remaining owner work

`make lint` and `pytest -q`: not run, per the instruction to run only the approved
infrastructure checks. GitHub-hosted workflow, AWS APIs, plan, apply, deployments,
application runtime checks and database/pgvector checks: not run.

Manual step M15: review this reference and its open findings on the PR. No account,
key, signup or deployment is needed. Do not remove the blocking findings or add
new skips merely to make CI green. Further TLS, WAF evidence and rotation work must
be scoped separately before calling security validation successful.
