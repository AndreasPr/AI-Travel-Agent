locals {
  services = toset(["api", "web"])
  trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = { StringEquals = { "aws:SourceAccount" = var.account_id } }
    }]
  })
}
resource "aws_iam_role" "task" {
  for_each           = local.services
  name               = "${var.name}-${each.key}-task"
  assume_role_policy = local.trust
  description        = "Application task role; no AWS API permissions are granted."
}
resource "aws_iam_role" "execution" {
  for_each           = local.services
  name               = "${var.name}-${each.key}-execution"
  assume_role_policy = local.trust
  description        = "Service-specific log delivery and API-only secret injection."
}
resource "aws_iam_role_policy" "log_delivery" {
  # checkov:skip=CKV_AWS_355:Fargate runtime task IDs require a suffix wildcard only inside this service's log stream prefix; reviewed in docs/security-exceptions.md.
  for_each = local.services
  name     = "${var.name}-${each.key}-log-delivery"
  role     = aws_iam_role.execution[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "OwnServiceLogStreams"
      Effect = "Allow"
      Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
      # Sole resource wildcard exception: awslogs appends the runtime task ID.
      # Restricted to this service's own group and prefix/container pair.
      Resource = ["${trimsuffix(var.log_group_arns[each.key], ":*")}:log-stream:${each.key}/${each.key}/*"]
    }]
  })
}
resource "aws_iam_role_policy" "api_secrets" {
  name = "${var.name}-api-secret-injection"
  role = aws_iam_role.execution["api"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = var.api_secret_arns
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [var.kms_key_arn]
        Condition = { StringEquals = {
          "kms:ViaService"                  = "secretsmanager.${var.region}.amazonaws.com"
          "kms:EncryptionContext:SecretARN" = var.api_secret_arns
        } }
      }
    ]
  })
}
