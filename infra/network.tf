resource "google_compute_network" "vpc" {
  name                    = "pie-slice"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "subnet" {
  name                     = "pie-slice"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Only IAP's TCP-forwarding range may reach SSH. Nothing else inbound; the
# app is reached over Tailscale, which dials out.
resource "google_compute_firewall" "iap_ssh" {
  name      = "pie-slice-allow-iap-ssh"
  network   = google_compute_network.vpc.name
  direction = "INGRESS"

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["pie-slice"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# The VM has no external IP. Cloud NAT gives it outbound access (apt, Docker
# and Tailscale packages, the Tailscale control plane). A static/ephemeral
# external IPv4 is billed too and would make the VM directly addressable.
resource "google_compute_router" "router" {
  name    = "pie-slice"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "pie-slice"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
