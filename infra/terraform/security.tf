resource "aws_vpc_security_group_egress_rule" "alb" {
  for_each                     = { api = 8080, web = 3000 }
  security_group_id            = module.alb.security_group_id
  referenced_security_group_id = module.compute.security_group_ids[each.key]
  description                  = "ALB to service port only."
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}
resource "aws_vpc_security_group_egress_rule" "database" {
  security_group_id            = module.compute.security_group_ids["api"]
  referenced_security_group_id = module.database.security_group_id
  description                  = "API to PostgreSQL only."
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}
