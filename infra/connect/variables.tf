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

variable "admin_name" {
  description = "Name shown to members when they must contact the group administrator"
  type        = string
  default     = "la administradora del grupo"
}
