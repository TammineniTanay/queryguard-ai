from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from google.cloud import bigquery


class BigQueryAdapter:
    """Production execution adapter.

    Requires Application Default Credentials or a workload identity in production.
    For every query, do a dry run first, cap bytes billed, then execute.
    """

    def __init__(self) -> None:
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("BIGQUERY_LOCATION", "US")
        self.max_bytes_billed = int(os.getenv("MAX_BYTES_BILLED", "1000000000"))
        self.client = bigquery.Client(project=self.project, location=self.location)

    def execute(self, sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        dry_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            maximum_bytes_billed=self.max_bytes_billed,
            labels={"app": "queryguard", "mode": "dryrun"},
        )
        dry_job = self.client.query(sql, job_config=dry_config)
        if dry_job.total_bytes_processed and dry_job.total_bytes_processed > self.max_bytes_billed:
            raise RuntimeError(
                f"Query would process {dry_job.total_bytes_processed} bytes, above MAX_BYTES_BILLED={self.max_bytes_billed}"
            )

        run_config = bigquery.QueryJobConfig(
            use_query_cache=True,
            maximum_bytes_billed=self.max_bytes_billed,
            labels={"app": "queryguard", "mode": "execute"},
        )
        job = self.client.query(sql, job_config=run_config)
        result = job.result()
        columns = [field.name for field in result.schema]
        rows = [dict(row.items()) for row in result]
        return columns, rows
