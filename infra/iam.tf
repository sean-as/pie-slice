resource "google_service_account" "vm" {
  account_id   = "pie-slice-vm"
  display_name = "pie-slice VM"

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "deployer" {
  account_id   = "pie-slice-deployer"
  display_name = "pie-slice GitHub Actions deployer"

  depends_on = [google_project_service.apis]
}

# ---- vm ----
resource "google_artifact_registry_repository_iam_member" "vm_pull" {
  repository = google_artifact_registry_repository.app.name
  location   = google_artifact_registry_repository.app.location
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_storage_bucket_iam_member" "vm_backups" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_metrics" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# ---- deployer ----
resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  repository = google_artifact_registry_repository.app.name
  location   = google_artifact_registry_repository.app.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_iap_tunnel_instance_iam_member" "deployer_tunnel" {
  project  = var.project_id
  zone     = var.zone
  instance = google_compute_instance.vm.name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = "serviceAccount:${google_service_account.deployer.email}"

  lifecycle {
    replace_triggered_by = [google_compute_instance.vm.id]
  }
}

# Docker access on the VM is root-equivalent anyway, so admin login is no
# extra power; it is scoped to this one instance.
resource "google_compute_instance_iam_member" "deployer_login" {
  project       = var.project_id
  zone          = var.zone
  instance_name = google_compute_instance.vm.name
  role          = "roles/compute.osAdminLogin"
  member        = "serviceAccount:${google_service_account.deployer.email}"

  lifecycle {
    replace_triggered_by = [google_compute_instance.vm.id]
  }
}

resource "google_project_iam_member" "deployer_viewer" {
  project = var.project_id
  role    = "roles/compute.viewer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# OS Login over SSH requires act-as on the VM's own service account.
resource "google_service_account_iam_member" "deployer_acts_as_vm" {
  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
