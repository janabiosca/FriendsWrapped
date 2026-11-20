"""Run bounded, predefined Athena queries against the private raw listening archive."""
import argparse
from datetime import date
import json
from pathlib import Path
import re
import time

import boto3

SQL_DIRECTORY = Path(__file__).resolve().parents[1] / "analytics" / "sql"
QUERIES = ("counts", "top_artists", "monthly")


def render_query(database, query, start_date, end_date):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,254}", database):
        raise ValueError("Invalid database identifier")
    if query not in QUERIES:
        raise ValueError("Unknown predefined query")
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start.isoformat() != start_date or end.isoformat() != end_date or start > end:
        raise ValueError("Use YYYY-MM-DD archive dates with start <= end")
    sql = (SQL_DIRECTORY / "query.sql").read_text()
    for key, value in {"database": database, "start_date": start_date,
                       "end_date": end_date,
                       "analysis": (SQL_DIRECTORY / f"{query}.sql").read_text()}.items():
        sql = sql.replace("{{" + key + "}}", value)
    return sql


def execute(client, workgroup, database, sql, timeout=120):
    query_id = client.start_query_execution(
        QueryString=sql, QueryExecutionContext={"Database": database}, WorkGroup=workgroup
    )["QueryExecutionId"]
    deadline = time.monotonic() + timeout
    while True:
        execution = client.get_query_execution(QueryExecutionId=query_id)["QueryExecution"]
        state = execution["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Athena {state}: {execution['Status'].get('StateChangeReason', '')}")
        if time.monotonic() >= deadline:
            client.stop_query_execution(QueryExecutionId=query_id)
            raise TimeoutError(f"Athena query cancelled after timeout: {query_id}")
        time.sleep(1)
    rows, names = [], None
    for page in client.get_paginator("get_query_results").paginate(QueryExecutionId=query_id):
        if names is None:
            names = [column["Name"] for column in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
            data = page["ResultSet"]["Rows"][1:]  # header exists only on the first page
        else:
            data = page["ResultSet"]["Rows"]
        rows.extend({name: cell.get("VarCharValue") for name, cell in zip(names, row["Data"])} for row in data)
    return {"query_id": query_id, "bytes_scanned": execution.get("Statistics", {}).get("DataScannedInBytes", 0), "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="sfw_dev_analytics")
    parser.add_argument("--workgroup", default="sfw-dev-analytics")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--query", choices=QUERIES, default="top_artists")
    parser.add_argument("--start-date", required=True, help="First archive collection date, UTC")
    parser.add_argument("--end-date", required=True, help="Last archive collection date, UTC (inclusive)")
    args = parser.parse_args()
    sql = render_query(args.database, args.query, args.start_date, args.end_date)
    print(json.dumps(execute(boto3.client("athena", region_name=args.region), args.workgroup, args.database, sql), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
