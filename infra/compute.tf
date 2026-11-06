locals {
  data_device_name = "pie-slice-data"
}

# Separate from the boot disk so replacing the VM never touches the database.
resource "google_compute_disk" "data" {
  name = "pie-slice-data"
  type = "pd-standard"
  zone = var.zone
  size = var.data_disk_gb

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_compute_instance" "vm" {
  name         = var.vm_name
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["pie-slice"]

  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      type  = "pd-standard"
      size  = var.boot_disk_gb
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = local.data_device_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.id
    # No access_config: no external IP. Egress goes through Cloud NAT.
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin = "TRUE"
    # "startup-script" (not metadata_startup_script) so editing it does not
    # force the VM to be replaced. Re-run it with:
    #   sudo google_metadata_script_runner startup
    startup-script = templatefile("${path.module}/startup.sh.tftpl", {
      project_id       = var.project_id
      registry_host    = "${var.region}-docker.pkg.dev"
      image_repo       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}/pie-slice"
      data_device_name = local.data_device_name
      hostname         = var.vm_name
      tailscale_tag    = var.tailscale_tag
      tailscale_secret = google_secret_manager_secret.this["tailscale-auth-key"].secret_id
    })
  }

  lifecycle {
    # A new Debian image release must not replace the VM.
    ignore_changes = [boot_disk[0].initialize_params[0].image]
  }

  depends_on = [
    google_compute_router_nat.nat,
    google_secret_manager_secret_iam_member.vm_access,
    google_artifact_registry_repository_iam_member.vm_pull,
  ]
}
