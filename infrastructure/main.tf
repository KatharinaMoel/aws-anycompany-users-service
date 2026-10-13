terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

# No region argument: the provider reads the region from the AWS_REGION environment variable.
provider "aws" {
  default_tags {
    tags = {
      Project = "anycompany-users-service"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  name_prefix = var.name_prefix
  account_id  = data.aws_caller_identity.current.account_id
}
