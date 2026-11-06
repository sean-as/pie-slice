# Infrastructure

Terraform for one `e2-micro` VM (no external IP, reached over Tailscale),
Artifact Registry, Secret Manager containers, a backup bucket, Workload
Identity for GitHub Actions, and a budget alert. The code is public; state and
real values are not (see "What lives where" in `IMPLEMENTATION-PLAN.md`).

## Bootstrap (once, by hand)

```sh
gcloud projects create PROJECT_ID
gcloud billing projects link PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
gcloud services enable serviceusage.googleapis.com cloudresourcemanager.googleapis.com --project=PROJECT_ID

# Private, versioned state bucket
gcloud storage buckets create gs://PROJECT_ID-tfstate --project=PROJECT_ID \
  --location=us-central1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://PROJECT_ID-tfstate --versioning
```

Your own account needs Owner on the project and Billing Account
Administrator (or Costs Manager) on the billing account for the budget.

```sh
cd infra
cp terraform.tfvars.example terraform.tfvars   # edit
cp backend.hcl.example backend.hcl             # edit
terraform init -backend-config=backend.hcl
terraform apply
```

## After the first apply

1. **Tailscale.** In the admin console enable MagicDNS and HTTPS
   certificates (`tailscale serve` fails without them), define the ACL tag
   (`tag:pie-slice`), and create a tagged auth key. Then:
   ```sh
   printf '%s' "$KEY" | gcloud secrets versions add tailscale-auth-key --data-file=- --project=PROJECT_ID
   gcloud compute ssh pie-slice --tunnel-through-iap --zone=ZONE --project=PROJECT_ID \
     --command='sudo google_metadata_script_runner startup'
   ```
2. **Actions variables.** `terraform output` prints `GCP_PROJECT_ID`,
   `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOYER_SA`, `VM_NAME`, `VM_ZONE`,
   `AR_REPOSITORY`. Add each as a GitHub Actions **variable** (not a secret).
3. Heartbeat URL (phase 2): same `gcloud secrets versions add` flow for
   `heartbeat-url`.

## Recovery

If the boot disk is recreated, Tailscale login state is lost and a single-use
key is spent: add a fresh key to `tailscale-auth-key`, delete the old node in
the Tailscale admin console (or the new one registers as `pie-slice-1` and the
URL changes), then re-run the startup script. The data disk and database are
untouched.

## Notes

- The budget currency is `USD`; it must match the billing account's currency.
- The VM's service account has `objectAdmin` on the backup bucket (it needs to
  upload and prune). Consider object versioning if backup tampering matters.

- Outbound traffic goes through Cloud NAT (billed, a few dollars/month); the
  VM has no external IP. Swap for an ephemeral IP in `network.tf`/`compute.tf`
  if you prefer, but that is also billed and exposes the VM directly.
- The startup script is idempotent and runs on every boot. Editing it does not
  replace the VM; re-run it with `sudo google_metadata_script_runner startup`.
- The deploy job copies `compose.yaml` to `/opt/pie-slice/` and runs docker
  via `sudo`. The startup script writes `/opt/pie-slice/.env` once (with
  `IMAGE_REPO`).
- `prevent_destroy` guards the data disk and backup bucket. The Workload
  Identity pool and provider IDs are soft-deleted for 30 days if destroyed.
- CI only runs `terraform fmt -check` and `terraform validate`
  (`init -backend=false`). Never run `plan` in Actions on this public repo.
