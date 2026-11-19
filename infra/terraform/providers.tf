provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project = var.name
      Status  = "validated-not-deployed"
    }
  }
}
