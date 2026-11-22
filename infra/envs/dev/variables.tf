variable "region" {
  type    = string
  default = "us-east-1"
}

variable "spotify_client_id" {
  description = "Client ID of the Spotify app"
  type        = string
}

variable "alarm_email" {
  description = "Receives the collection alarms (empty = none)"
  type        = string
  default     = ""
}

variable "collect_schedule" {
  description = "Use rate(5 minutes) for the demo"
  type        = string
  default     = "rate(1 hour)"
}

variable "existing_raw_bucket" {
  description = "Raw bucket created outside Terraform (AWS Academy denies GetBucketObjectLockConfiguration, see ADR 005)"
  type        = string
  validation {
    condition     = length(var.existing_raw_bucket) > 0
    error_message = "Create the raw bucket first and pass its name (TF_VAR_existing_raw_bucket or terraform.tfvars)."
  }
}
