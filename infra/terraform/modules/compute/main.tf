locals {
  ports              = { api = 8080, web = 3000 }
  security_group_ids = { api = aws_security_group.api.id, web = aws_security_group.web.id }
}
resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}
resource "aws_ecs_task_definition" "service" {
  for_each                 = local.ports
  family                   = "${var.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = var.execution_role_arns[each.key]
  task_role_arn            = var.task_role_arns[each.key]
  volume {
    name = "scratch"
  }
  container_definitions = jsonencode([{
    name                   = each.key
    image                  = var.images[each.key]
    essential              = true
    readonlyRootFilesystem = true
    user                   = "1000"
    privileged             = false
    portMappings           = [{ containerPort = each.value, hostPort = each.value, protocol = "tcp" }]
    mountPoints            = [{ sourceVolume = "scratch", containerPath = "/tmp", readOnly = false }]
    linuxParameters        = { capabilities = { drop = ["ALL"] } }
    environment = each.key == "api" ? [
      { name = "APP_ENV", value = "production" },
      { name = "FRONTEND_ORIGINS", value = var.frontend_origin }
    ] : []
    secrets = each.key == "api" ? [for name, arn in var.api_secret_arns : { name = name, valueFrom = arn }] : []
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = var.log_group_names[each.key]
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
    healthCheck = {
      command     = each.key == "api" ? ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8080/healthz\")' || exit 1"] : ["CMD-SHELL", "node -e 'fetch(\"http://localhost:3000/\").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))' "]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}
resource "aws_ecs_service" "api" {
  name                               = "api"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.service["api"].arn
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  desired_count                      = var.desired_count
  enable_execute_command             = false
  enable_ecs_managed_tags            = true
  propagate_tags                     = "TASK_DEFINITION"
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.target_group_arns["api"]
    container_name   = "api"
    container_port   = 8080
  }
}

resource "aws_ecs_service" "web" {
  name                               = "web"
  cluster                            = aws_ecs_cluster.this.id
  task_definition                    = aws_ecs_task_definition.service["web"].arn
  launch_type                        = "FARGATE"
  platform_version                   = "LATEST"
  desired_count                      = var.desired_count
  enable_execute_command             = false
  enable_ecs_managed_tags            = true
  propagate_tags                     = "TASK_DEFINITION"
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.web.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = var.target_group_arns["web"]
    container_name   = "web"
    container_port   = 3000
  }
}


resource "aws_security_group" "api" {
  name_prefix = "${var.name}-api-"
  description = "Only ALB ingress to this service's application port."
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "web" {
  name_prefix = "${var.name}-web-"
  description = "Only ALB ingress to this service's application port."
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "task" {
  for_each                     = local.ports
  security_group_id            = local.security_group_ids[each.key]
  referenced_security_group_id = var.alb_security_group_id
  description                  = "ALB to service port only."
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}
resource "aws_vpc_security_group_egress_rule" "https" {
  for_each          = { for pair in setproduct(keys(local.ports), var.egress_cidrs) : "${pair[0]}-${pair[1]}" => pair }
  security_group_id = local.security_group_ids[each.value[0]]
  description       = "Operator-approved HTTPS destination only."
  cidr_ipv4         = each.value[1]
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
