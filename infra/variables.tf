variable "project_id" {
  description = "GCP project that hosts everything."
  type        = string
}

variable "region" {
  description = "Free-tier e2-micro regions: us-west1, us-central1, us-east1."
  type        = string
  default     = "us-central1"

  validation {
    condition     = contains(["us-west1", "us-central1", "us-east1"], var.region)
    error_message = "Use a free-tier e2-micro region."
  }
}

variable "zone" {
  type    = string
  default = "us-central1-a"

  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must be inside region."
  }
}

variable "github_repository_id" {
  description = "Numeric GitHub repository ID (immutable, unlike the name). `gh api repos/OWNER/REPO --jq .id`"
  type        = string
}

variable "vm_name" {
  description = "VM name; also the Tailscale hostname."
  type        = string
  default     = "pie-slice"
}

variable "tailscale_tag" {
  description = "ACL tag the Tailscale auth key is scoped to (tagged nodes have key expiry off). Empty to skip --advertise-tags."
  type        = string
  default     = "tag:pie-slice"
}

variable "boot_disk_gb" {
  type    = number
  default = 10
}

variable "data_disk_gb" {
  description = "Boot + data must total 30 GB to stay in the free tier."
  type        = number
  default     = 20

  validation {
    condition     = var.boot_disk_gb + var.data_disk_gb <= 30
    error_message = "Over 30 GB of standard disk leaves the free tier."
  }
}

variable "billing_account_id" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX) for the budget alert."
  type        = string
}

variable "budget_usd" {
  description = "Monthly budget in USD; alerts at 50%, 90% and 100%."
  type        = number
  default     = 10
}
