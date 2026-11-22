variable "aws_region" {
  type    = string
  default = "us-east-1"
}
variable "name_prefix" {
  type    = string
  default = "sfw-dev"
}
variable "lab_role_name" {
  type    = string
  default = "LabRole"
}
variable "table_name" {
  type    = string
  default = "sfw-dev"
}
variable "group_id" {
  type    = string
  default = "friends"
}
variable "raw_bucket_name" {
  description = "Existing ingestion raw bucket; read from the ingestion raw_bucket output."
  type        = string
}
variable "alarm_topic_arn" {
  description = "Existing ingestion SNS alarm topic ARN."
  type        = string
}

variable "dashboard_url" {
  description = "Existing authenticated dashboard home URL, used in availability notices."
  type        = string
  validation {
    condition     = can(regex("^https://[A-Za-z0-9.-]+/?$", var.dashboard_url))
    error_message = "Supply the HTTPS dashboard home URL without query parameters."
  }
}

variable "wrapped_notice_emails" {
  description = "Recipients of weekly availability notices. Each recipient confirms their SNS subscription."
  type        = set(string)
  default     = []
}

variable "scheduler_dlq_enabled" {
  description = "Enable after confirming the schedule execution role can send messages to the scheduler DLQ."
  type        = bool
  default     = false
}
