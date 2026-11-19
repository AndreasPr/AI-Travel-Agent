module "network" {
  source              = "./modules/network"
  name                = var.name
  availability_zones  = var.availability_zones
  vpc_cidr            = var.vpc_cidr
  default_route_cidr  = var.default_route_cidr
  enable_nat          = var.enable_nat
  flow_log_bucket_arn = var.flow_log_bucket_arn
}

module "logs" {
  source      = "./modules/logs"
  name        = var.name
  kms_key_arn = var.kms_key_arn
}

module "secrets" {
  source      = "./modules/secrets"
  name        = var.name
  kms_key_arn = var.kms_key_arn
}

module "iam" {
  source          = "./modules/iam"
  name            = var.name
  region          = var.region
  account_id      = var.account_id
  log_group_arns  = module.logs.arns
  api_secret_arns = values(module.secrets.arns)
  kms_key_arn     = var.kms_key_arn
}

module "database" {
  source                = "./modules/database"
  name                  = var.name
  private_subnet_ids    = module.network.private_subnet_ids
  kms_key_arn           = var.kms_key_arn
  monitoring_role_arn   = var.monitoring_role_arn
  vpc_id                = module.network.vpc_id
  api_security_group_id = module.compute.security_group_ids["api"]
  engine_version        = var.postgres_version
  parameter_family      = var.postgres_parameter_family
}

module "alb" {
  source            = "./modules/alb"
  name              = var.name
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  client_cidrs      = var.client_cidrs
  certificate_arn   = var.certificate_arn
  log_bucket_name   = var.alb_log_bucket_name
  web_acl_arn       = var.web_acl_arn
}

module "compute" {
  source                = "./modules/compute"
  name                  = var.name
  region                = var.region
  private_subnet_ids    = module.network.private_subnet_ids
  vpc_id                = module.network.vpc_id
  alb_security_group_id = module.alb.security_group_id
  egress_cidrs          = var.egress_cidrs
  execution_role_arns   = module.iam.execution_role_arns
  task_role_arns        = module.iam.task_role_arns
  log_group_names       = module.logs.names
  target_group_arns     = module.alb.target_group_arns
  images                = var.images
  api_secret_arns       = module.secrets.arns
  frontend_origin       = var.frontend_origin
  desired_count         = var.desired_count
  depends_on            = [module.alb]
}
