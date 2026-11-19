# Entries only: no secret versions, passwords, or API keys are supplied by Terraform.
resource "aws_secretsmanager_secret" "entry" {
  for_each                = toset(["JWT_SECRET", "DATABASE_URL"])
  name                    = "${var.name}/${each.key}"
  description             = "Empty API runtime secret entry; value provisioned outside Terraform."
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 30
}
