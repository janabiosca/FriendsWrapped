# AWS Academy hosts the current real history. Credentials expire with the lab session;
# continued operation is not guaranteed. The optional prod configuration is not deployed.
module "ingestion" {
  source = "../../modules/ingestion"

  existing_raw_bucket  = "sfw-dev-raw-6e5880d28f5d8e514bf6ee4650"
  name                 = "sfw-dev"
  spotify_client_id    = var.spotify_client_id
  alarm_email          = var.alarm_email
  collect_schedule     = var.collect_schedule
  lab_role_name        = "LabRole"
  protect_data         = false # no deletion protection: inspect destruction plans carefully; this is real history
  customer_managed_key = false # AWS managed encryption: LabRole may not be allowed to use our own keys
  log_retention_days   = 7

  source_dir = "${path.root}/../../../src"
  build_dir  = "${path.root}/.build"
}
