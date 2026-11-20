mock_provider "aws" {}
run "private_bounded_analytics" {
  command = plan
  variables {
    raw_bucket_name = "test-private-archive"
    listener_ids    = ["listener-a", "listener-b"]
  }
  assert {
    condition     = aws_glue_catalog_table.raw_pages.parameters["storage.location.template"] == "s3://test-private-archive/raw/provider=spotify/user=$${listener}/dt=$${collection_date}/"
    error_message = "Partition projection must map existing ingestion paths without moving raw objects."
  }
  assert {
    condition     = aws_athena_workgroup.analytics.configuration[0].enforce_workgroup_configuration && aws_athena_workgroup.analytics.configuration[0].bytes_scanned_cutoff_per_query == 104857600
    error_message = "The workgroup must enforce the per-query scan limit."
  }
  assert {
    condition     = aws_athena_workgroup.analytics.configuration[0].result_configuration[0].encryption_configuration[0].encryption_option == "SSE_S3"
    error_message = "Query results must be encrypted."
  }
  assert {
    condition     = !strcontains(aws_glue_catalog_table.raw_pages.parameters["projection.listener.values"], "jana")
    error_message = "The catalog must use configured listener partitions."
  }
}
