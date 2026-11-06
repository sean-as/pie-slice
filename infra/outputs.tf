# Copy these into GitHub Actions *variables* (Settings > Secrets and variables
# > Actions > Variables). They are identifiers, not credentials.
output "GCP_PROJECT_ID" {
  value = var.project_id
}

output "GCP_REGION" {
  value = var.region
}

output "GCP_WIF_PROVIDER" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "GCP_DEPLOYER_SA" {
  value = google_service_account.deployer.email
}

output "VM_NAME" {
  value = google_compute_instance.vm.name
}

output "VM_ZONE" {
  value = var.zone
}

output "AR_REPOSITORY" {
  value = google_artifact_registry_repository.app.repository_id
}

output "backup_bucket" {
  value = google_storage_bucket.backups.name
}
