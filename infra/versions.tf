terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Real bucket comes from backend.hcl (gitignored):
  #   terraform init -backend-config=backend.hcl
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # The Budgets API is billed/quota'd against a project, not the caller.
  user_project_override = true
  billing_project       = var.project_id
}
