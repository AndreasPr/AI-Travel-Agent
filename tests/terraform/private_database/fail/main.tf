# Synthetic adversarial policy fixture: must fail CKV_AWS_17.
resource "aws_db_instance" "synthetic_public" {
  publicly_accessible = true
}
