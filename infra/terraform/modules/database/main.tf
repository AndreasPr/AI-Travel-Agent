resource "aws_db_subnet_group" "private" {
  name        = "${var.name}-private"
  description = "Private subnets only, in two availability zones."
  subnet_ids  = var.private_subnet_ids
}
resource "aws_db_parameter_group" "tls" {
  name_prefix = "${var.name}-"
  family      = var.parameter_family
  description = "Require TLS for PostgreSQL clients."
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}
resource "aws_db_instance" "postgres" {
  identifier                            = var.name
  engine                                = "postgres"
  engine_version                        = var.engine_version
  instance_class                        = "db.t4g.micro"
  allocated_storage                     = 20
  max_allocated_storage                 = 100
  storage_type                          = "gp3"
  storage_encrypted                     = true
  kms_key_id                            = var.kms_key_arn
  db_name                               = "travel"
  username                              = "travel_admin"
  manage_master_user_password           = true
  master_user_secret_kms_key_id         = var.kms_key_arn
  db_subnet_group_name                  = aws_db_subnet_group.private.name
  vpc_security_group_ids                = [aws_security_group.database.id]
  parameter_group_name                  = aws_db_parameter_group.tls.name
  publicly_accessible                   = false
  multi_az                              = true
  backup_retention_period               = 7
  backup_window                         = "03:00-04:00"
  maintenance_window                    = "sun:05:00-sun:06:00"
  auto_minor_version_upgrade            = true
  allow_major_version_upgrade           = false
  deletion_protection                   = true
  skip_final_snapshot                   = false
  final_snapshot_identifier             = "${var.name}-final"
  copy_tags_to_snapshot                 = true
  iam_database_authentication_enabled   = true
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]
  monitoring_interval                   = 60
  monitoring_role_arn                   = var.monitoring_role_arn
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = var.kms_key_arn
  performance_insights_retention_period = 7
}

resource "aws_security_group" "database" {
  name_prefix = "${var.name}-database-"
  description = "Only API tasks may connect to PostgreSQL."
  vpc_id      = var.vpc_id
}
resource "aws_vpc_security_group_ingress_rule" "database" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = var.api_security_group_id
  description                  = "API to PostgreSQL only."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
