# Terraform reference infrastructure

validated, not deployed

This is a validation-only reference, not a deployment-ready environment. No AWS
account was accessed, and no plan, apply, remote backend or deployment is part of
this task or CI. Applying these resources would incur AWS charges; they are not
claimed to be free-tier infrastructure. Only local/CI validation is free.
See `VALIDATION.md` for actual command results and unresolved security findings.

## Layout and interfaces

| Module | Resources / boundaries |
|---|---|
| network | VPC, two public and two private subnets in two caller-selected AZs, route tables, Internet gateway, optional per-AZ NAT, closed default SG, flow logs to an existing S3 destination |
| database | Private, encrypted, multi-AZ RDS PostgreSQL, seven-day backups, TLS parameter group, managed master password, deletion protection and final snapshot |
| compute | Private Fargate API and web tasks/services, separate SGs, no public task addresses, health checks, read-only root filesystem, zero desired tasks by default |
| alb | Public ALB restricted to approved clients, HTTPS certificate input, HTTP redirect, API path routing, access logs and association with an existing WAF ACL |
| secrets | KMS-encrypted JWT_SECRET and DATABASE_URL entries, with no values or versions |
| iam | Separate execution and permissionless application task roles; API-only secret injection, constrained KMS decryption, own-service log delivery |
| logs | KMS-encrypted API/web CloudWatch groups with 365-day retention and retention on Terraform removal |

Root `security.tf` connects ALB egress to the two exact task SGs and API egress to
the database SG. Database ingress is API-only on TCP 5432; web has no database rule.
ALB ingress is TCP 80/443 from `client_cidrs`; the default empty set denies access.
Task internet egress is TCP 443 only to `egress_cidrs`, also empty by default.
Unrestricted CIDRs are rejected by the root input validations. No SSH/RDP rules,
public database addresses, public task addresses or unrestricted SG egress exist.

IAM policy: no standalone wildcard resources; one scoped log-stream exception, documented.
The sole suffix wildcard belongs to `aws_iam_role_policy.log_delivery` and permits
only logs:CreateLogStream and logs:PutLogEvents under the service's own group and
`api/api/` or `web/web/` prefix. See ../../docs/security-exceptions.md.
No wildcard actions, AWS-managed broad execution policies or ECR authorization
permissions are included. Public registry images must be supplied by immutable digest;
private ECR pulls are not supported by these intentionally restricted roles.

## Validation without credentials

Tools used: Terraform 1.5.7, AWS provider **6.42.0**, TFLint 0.65.0 (built-in Terraform
recommended rules), Checkov **3.3.30**, Python 3.12. Provider versions are exact in
required_providers. Commit `.terraform.lock.hcl`; `.terraform/`, state, plans and
actual tfvars are ignored. Do not configure a backend or AWS credentials.

From the repository root:

```sh
terraform -chdir=infra/terraform fmt -check -recursive
terraform -chdir=infra/terraform init -backend=false -input=false -lockfile=readonly
terraform -chdir=infra/terraform validate -no-color
tflint --chdir=infra/terraform --recursive --config="$PWD/infra/terraform/.tflint.hcl"
```

Install Checkov only in a temporary environment, never into application requirements:

```sh
CHECKOV_ENV="$(mktemp -d /tmp/travel-terraform-checkov.XXXXXX)"
python3.12 -m venv "$CHECKOV_ENV"
"$CHECKOV_ENV/bin/pip" install checkov==3.3.30
"$CHECKOV_ENV/bin/checkov" -d infra/terraform --framework terraform --skip-download --download-external-modules false --compact
# Preserve the scanner's exit status before removing the temporary environment.
CHECKOV_RESULT=$?
rm -rf "$CHECKOV_ENV"
printf 'Checkov exit: %s\n' "$CHECKOV_RESULT"
```

Checkov runs without a platform/API key. Because offline policies can lack severity
metadata, CI fails **all** non-skipped findings rather than silently passing unscored
ones through a HIGH-only filter. No soft-fail, broad check exclusion or secret is used.
The one approved inline suppression is CKV_AWS_355 on log_delivery (one resource
template, two service instances). The security job remains red for other findings.
Synthetic fixtures in `tests/terraform/private_database/` exercise CKV_AWS_17:
private must pass and public must fail. They are policy tests, not deployed databases.

## Inputs and non-deployment prerequisites

`terraform.tfvars.example` contains placeholders, not working account IDs, ARNs,
network addresses, image digests or credentials. Validation does not need tfvars;
do not turn the example into committed real values. No environment/account values
have been discovered or invented. Root variables document all inputs and outputs.

Before any separately authorized deployment work, an operator would need to resolve:

- Actual AZ/CIDR choices, ACM certificate/domain, reviewed KMS key policy, private
  flow-log and ALB-log buckets with correct delivery policies, an RDS monitoring
  role, and a WAF ACL containing the required managed protections. Existing-resource
  ownership, policies and reachability are **not verified** by Terraform validate.
- NAT is OFF and no VPC endpoints are created. Private tasks cannot pull public
  images or reach external providers by default. Interface endpoints for Logs and
  Secrets Manager (and KMS when directly needed) or an approved NAT/HTTPS path would
  be needed. ECR would additionally require API/DKR endpoints and an S3 gateway,
  plus a separately reviewed authorization-policy exception; it is not wired here.
- Secret values, application database user/privileges, migration/seed and rotation
  implementation are intentionally absent. RDS manages its own master credential;
  that master credential is not injected into the application. Empty application
  secrets cannot start tasks. Never put secret versions or values in this Terraform.
- Correct runtime image architecture, non-root file permissions, writable cache
  mounts, packaged local models, database CA/TLS connection settings and the web
  image's build-time API URL require runtime verification. None was tested here.
- ALB terminates TLS; backend application ports remain HTTP because the existing
  containers do not terminate TLS. End-to-end TLS needs separate application/proxy
  work; its Checkov finding is left blocking, not disguised as HTTPS.
- Review final snapshot naming before any deletion, and review security findings
  and the log-stream exception before its stated review date.

Outputs expose resource identifiers/endpoints only. There are no secret-value outputs.
This reference does not establish service availability, image pull access, pgvector
installation, account quotas, current pricing, or application deployment correctness.
