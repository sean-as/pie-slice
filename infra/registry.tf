resource "google_artifact_registry_repository" "app" {
  repository_id = "pie-slice"
  location      = var.region
  format        = "DOCKER"
  description   = "pie-slice application images"

  cleanup_policy_dry_run = false

  # KEEP beats DELETE, so the 10 newest versions always survive.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.apis]
}
