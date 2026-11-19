locals {
  zones = { for index, zone in var.availability_zones : tostring(index) => zone }
}
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.name }
}
resource "aws_default_security_group" "closed" {
  vpc_id  = aws_vpc.this.id
  ingress = []
  egress  = []
}
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}
resource "aws_subnet" "public" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, tonumber(each.key))
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-public-${each.key}", Tier = "public" }
}
resource "aws_subnet" "private" {
  for_each                = local.zones
  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, tonumber(each.key) + 2)
  map_public_ip_on_launch = false
  tags                    = { Name = "${var.name}-private-${each.key}", Tier = "private" }
}
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
}
resource "aws_route" "internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = var.default_route_cidr
  gateway_id             = aws_internet_gateway.this.id
}
resource "aws_route_table_association" "public" {
  for_each       = local.zones
  subnet_id      = aws_subnet.public[each.key].id
  route_table_id = aws_route_table.public.id
}
resource "aws_route_table" "private" {
  for_each = local.zones
  vpc_id   = aws_vpc.this.id
}
resource "aws_route_table_association" "private" {
  for_each       = local.zones
  subnet_id      = aws_subnet.private[each.key].id
  route_table_id = aws_route_table.private[each.key].id
}
resource "aws_eip" "nat" {
  for_each = var.enable_nat ? local.zones : {}
  domain   = "vpc"
}
resource "aws_nat_gateway" "optional" {
  for_each      = var.enable_nat ? local.zones : {}
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  depends_on    = [aws_internet_gateway.this]
}
resource "aws_route" "private_nat" {
  for_each               = var.enable_nat ? local.zones : {}
  route_table_id         = aws_route_table.private[each.key].id
  destination_cidr_block = var.default_route_cidr
  nat_gateway_id         = aws_nat_gateway.optional[each.key].id
}
resource "aws_flow_log" "this" {
  vpc_id               = aws_vpc.this.id
  traffic_type         = "ALL"
  log_destination_type = "s3"
  log_destination      = var.flow_log_bucket_arn
}
