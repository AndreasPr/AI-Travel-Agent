resource "aws_lb" "this" {
  name                       = var.name
  internal                   = false
  load_balancer_type         = "application"
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  desync_mitigation_mode     = "strictest"
  enable_deletion_protection = true
  access_logs {
    bucket  = var.log_bucket_name
    prefix  = var.name
    enabled = true
  }
}
resource "aws_lb_target_group" "service" {
  for_each    = { api = 8080, web = 3000 }
  name        = "${var.name}-${each.key}"
  vpc_id      = var.vpc_id
  port        = each.value
  protocol    = "HTTP"
  target_type = "ip"
  health_check {
    path    = each.key == "api" ? "/healthz" : "/"
    matcher = "200-399"
  }
}
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service["web"].arn
  }
}
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}
resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service["api"].arn
  }
  condition {
    path_pattern {
      values = ["/api/*", "/healthz", "/readyz", "/rag/search"]
    }
  }
}
resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = var.web_acl_arn
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-alb-"
  description = "Only approved clients on HTTP redirect and HTTPS."
  vpc_id      = var.vpc_id
}
resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each          = var.client_cidrs
  security_group_id = aws_security_group.alb.id
  description       = "Approved client HTTP redirect."
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}
resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each          = var.client_cidrs
  security_group_id = aws_security_group.alb.id
  description       = "Approved client HTTPS."
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
