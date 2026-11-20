terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "spotify-friends-wrapped"
      ManagedBy = "terraform"
    }
  }
}

resource "aws_glue_catalog_database" "listening" {
  name        = replace("${var.name_prefix}_analytics", "-", "_")
  description = "Private catalog of archived Spotify responses; source objects remain in the ingestion bucket."
}

resource "aws_glue_catalog_table" "raw_pages" {
  name          = "spotify_raw_pages"
  database_name = aws_glue_catalog_database.listening.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    EXTERNAL                                   = "TRUE"
    classification                             = "json"
    "projection.enabled"                       = "true"
    "projection.listener.type"                 = "enum"
    "projection.listener.values"               = join(",", sort(var.listener_ids))
    "projection.collection_date.type"          = "date"
    "projection.collection_date.range"         = "${var.first_archive_date},NOW"
    "projection.collection_date.format"        = "yyyy-MM-dd"
    "projection.collection_date.interval"      = "1"
    "projection.collection_date.interval.unit" = "DAYS"
    "storage.location.template"                = "s3://${var.raw_bucket_name}/raw/provider=spotify/user=$${listener}/dt=$${collection_date}/"
  }
  partition_keys {
    name = "listener"
    type = "string"
  }
  partition_keys {
    name = "collection_date"
    type = "string"
  }
  storage_descriptor {
    location      = "s3://${var.raw_bucket_name}/raw/provider=spotify/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    ser_de_info {
      name                  = "hive-json"
      serialization_library = "org.apache.hive.hcatalog.data.JsonSerDe"
    }
    columns {
      name = "items"
      type = "array<struct<played_at:string,track:struct<id:string,uri:string,name:string,duration_ms:bigint,artists:array<struct<id:string,name:string>>>>>"
    }
  }
}

resource "aws_athena_workgroup" "analytics" {
  name          = "${var.name_prefix}-analytics"
  description   = "Bounded SQL analysis of private listening archives."
  force_destroy = false
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.query_scan_limit_bytes
    engine_version {
      selected_engine_version = "Athena engine version 3"
    }
    result_configuration {
      output_location = "s3://${var.raw_bucket_name}/analytics-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

resource "aws_athena_named_query" "analysis" {
  for_each    = toset(["counts", "top_artists", "monthly"])
  name        = "${var.name_prefix}-${each.value}"
  database    = aws_glue_catalog_database.listening.name
  workgroup   = aws_athena_workgroup.analytics.name
  description = "Deduplicated plays; collection_date filters archive dates in UTC."
  query = replace(replace(replace(replace(
    file("${path.module}/../../analytics/sql/query.sql"),
    "{{database}}", aws_glue_catalog_database.listening.name),
    "{{start_date}}", var.first_archive_date),
    "{{end_date}}", "2099-12-31"),
  "{{analysis}}", file("${path.module}/../../analytics/sql/${each.value}.sql"))
}

output "database_name" {
  value = aws_glue_catalog_database.listening.name
}
output "workgroup_name" {
  value = aws_athena_workgroup.analytics.name
}
