# Containers and access only. Values are added out of band so they never
# land in Terraform state:
#   printf '%s' "$VALUE" | gcloud secrets versions add <name> --data-file=-
locals {
  secrets = toset([
    "tailscale-auth-key",
    "signup-code",   # invite code required to create an account
    "heartbeat-url", # phase 2 monitoring
  ])
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "vm_access" {
  for_each = local.secrets

  secret_id = google_secret_manager_secret.this[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}
