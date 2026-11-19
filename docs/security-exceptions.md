# Terraform security exceptions

## TF-LOG-001 — Fargate service log stream suffix

- Reviewed: 2026-11-19. Review date: **2026-12-19**.
- Scope: `infra/terraform/modules/iam/main.tf`, resource
  `aws_iam_role_policy.log_delivery` only. Its two instances are API and web.
- Checkov skip: **CKV_AWS_355** only, with the reason inline on that resource.
- Statement:

```hcl
Sid      = "OwnServiceLogStreams"
Effect   = "Allow"
Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
Resource = ["${trimsuffix(var.log_group_arns[each.key], ":*")}:log-stream:${each.key}/${each.key}/*"]
```

Fargate awslogs stream names contain runtime task IDs, unavailable when defining the
execution role. The suffix must therefore match future task IDs. The prefix is fixed
to the exact service-owned log group and service/container pair (`api/api/` or
`web/web/`). The role cannot write another service's group or stream prefix. It cannot
create groups, delete logs, read logs, use wildcard actions or use standalone
`Resource: "*"`. This is a narrowly scoped exception, not a blanket IAM suppression.
CKV_AWS_355 is the resource-policy check in pinned Checkov 3.3.30; CKV_AWS_356 is for
policy-document data sources and is not the applicable resource check here.
The skip is explicitly recorded even though a prefix-scoped statement need not be
flagged by every scanner version. Manual review must still reject scope expansion.

[AWS log stream naming](https://docs.aws.amazon.com/prescriptive-guidance/latest/implementing-logging-monitoring-cloudwatch/amazon-ecs-container-logs-for-ec2-and-fargate-launch-types.html).

No other Terraform Checkov skip or waiver is authorized. Open findings are listed
in `infra/terraform/VALIDATION.md`; they remain failures and are not exceptions.
