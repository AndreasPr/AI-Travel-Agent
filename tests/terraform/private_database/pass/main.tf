# Synthetic policy fixture: tests the guard, not a deployable database.
resource "aws_db_instance" "synthetic_private" {
  publicly_accessible = false
}
