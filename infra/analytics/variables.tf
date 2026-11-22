variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "name_prefix" {
  type    = string
  default = "sfw-dev"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,40}$", var.name_prefix))
    error_message = "Use a lowercase name prefix with letters, digits and hyphens."
  }
}
variable "raw_bucket_name" {
  description = "Existing private ingestion bucket; analytics does not own or delete it."
  type        = string
}
variable "listener_ids" {
  description = "Spotify listeners represented by S3 partitions; observers have no listening partitions."
  type        = set(string)
  validation {
    condition     = length(var.listener_ids) > 0 && alltrue([for id in var.listener_ids : can(regex("^[a-z0-9-]+$", id))])
    error_message = "Supply at least one listener ID consisting of lowercase letters, digits and hyphens."
  }
}
variable "first_archive_date" {
  type    = string
  default = "2026-11-01"
  validation {
    condition     = can(formatdate("YYYY-MM-DD", "${var.first_archive_date}T00:00:00Z"))
    error_message = "Use an existing archive start date in YYYY-MM-DD format."
  }
}
variable "query_scan_limit_bytes" {
  description = "Workgroup per-query scan cutoff; not a total account budget."
  type        = number
  default     = 104857600
  validation {
    condition     = var.query_scan_limit_bytes >= 10485760 && floor(var.query_scan_limit_bytes) == var.query_scan_limit_bytes
    error_message = "Athena requires an integer cutoff of at least 10 MiB."
  }
}
