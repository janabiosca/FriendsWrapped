"""Check bounded query rendering, cancellation and result pagination."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import query_analytics


@pytest.mark.parametrize("database,query,start,end", [
    ('db"; DROP DATABASE x', "counts", "2026-11-01", "2026-11-20"),
    ("test_db", "arbitrary-sql", "2026-11-01", "2026-11-20"),
    ("test_db", "counts", "2026-11-21", "2026-11-20"),
    ("test_db", "counts", "2026-11-01' OR 1=1 --", "2026-11-20"),
])
def test_untrusted_identifiers_and_date_ranges_rejected(database, query, start, end):
    with pytest.raises(ValueError):
        query_analytics.render_query(database, query, start, end)


def test_timeout_stops_the_running_query(monkeypatch):
    class Client:
        stopped = []
        def start_query_execution(self, **kwargs):
            return {"QueryExecutionId": "query-1"}
        def get_query_execution(self, **kwargs):
            return {"QueryExecution": {"Status": {"State": "RUNNING"}}}
        def stop_query_execution(self, **kwargs):
            self.stopped.append(kwargs["QueryExecutionId"])
    client = Client()
    with pytest.raises(TimeoutError):
        query_analytics.execute(client, "wg", "db", "SELECT 1", timeout=0)
    assert client.stopped == ["query-1"]


def test_results_keep_first_row_of_later_pages_and_nulls():
    class Client:
        def start_query_execution(self, **kwargs):
            return {"QueryExecutionId": "query-1"}
        def get_query_execution(self, **kwargs):
            return {"QueryExecution": {"Status": {"State": "SUCCEEDED"}, "Statistics": {"DataScannedInBytes": 123}}}
        def get_paginator(self, name):
            return self
        def paginate(self, **kwargs):
            yield {"ResultSet": {"ResultSetMetadata": {"ColumnInfo": [{"Name": "listener"}, {"Name": "plays"}]}, "Rows": [
                {"Data": [{"VarCharValue": "listener"}, {"VarCharValue": "plays"}]},
                {"Data": [{"VarCharValue": "a"}, {"VarCharValue": "2"}]}]}}
            yield {"ResultSet": {"Rows": [{"Data": [{"VarCharValue": "b"}, {}]}]}}
    result = query_analytics.execute(Client(), "wg", "db", "SELECT 1")
    assert result["rows"] == [{"listener": "a", "plays": "2"}, {"listener": "b", "plays": None}]
    assert result["bytes_scanned"] == 123
