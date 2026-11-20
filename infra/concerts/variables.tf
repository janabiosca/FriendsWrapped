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

variable "alarm_topic_arn" {
  description = "Existing ingestion SNS topic for operational alarms."
  type        = string
}

variable "concerts_enabled" {
  description = "Enable only after the Ticketmaster key is stored and a real scan is verified."
  type        = bool
  default     = false
}
