resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(["api", "web"])
  name              = "/ecs/${var.name}/${each.key}"
  retention_in_days = 365
  kms_key_id        = var.kms_key_arn
  skip_destroy      = true
}
