#!/usr/bin/env python3
"""
Alma Digital Collection Sync

Synchronizes Alma Digital Collections with MMS IDs from Analytics reports.
Every Alma call goes through almaapitk (header auth, retries, error handling):
- almaapitk.Analytics for report rows (pagination via ResumptionToken)
- almaapitk.BibliographicRecords for collection members, add and remove

Safety rule: a failed, empty or malformed report never changes a collection.
All reports are fetched and checked before any write.

Dependencies:
- almaapitk (pip install almaapitk)
- pyyaml
"""

import os
import yaml
import argparse
import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Dict, Any, Optional
from datetime import datetime

from almaapitk import AlmaAPIClient, Analytics, BibliographicRecords, AlmaAPIError

# Analytics column that holds the MMS ID (Column0 is Alma's hidden row column).
MMS_ID_COLUMN = "Column1"

# Page size for collection member reads (Alma maximum is 100).
MEMBERS_PAGE_SIZE = 100


class ReportError(Exception):
    """An Analytics report is empty or malformed; the sync must not proceed."""


@dataclass
class SyncPlan:
    """The changes needed to make a collection match its reports."""
    to_add: List[str] = field(default_factory=list)
    to_remove: List[str] = field(default_factory=list)


def plan_sync(report_mms_ids: Iterable[str], current_mms_ids: Iterable[str]) -> SyncPlan:
    """
    Compute what to add and remove so the collection matches the reports.

    An empty report set yields an empty plan: no report data means no
    evidence about what belongs in the collection, so nothing is removed.

    Args:
        report_mms_ids: MMS IDs from all reports (duplicates allowed)
        current_mms_ids: MMS IDs currently in the collection

    Returns:
        SyncPlan with sorted to_add and to_remove lists
    """
    report_set = set(report_mms_ids)
    if not report_set:
        return SyncPlan()

    current_set = set(current_mms_ids)
    return SyncPlan(
        to_add=sorted(report_set - current_set),
        to_remove=sorted(current_set - report_set),
    )


def extract_mms_ids(rows: List[Dict[str, Any]], report_path: str) -> List[str]:
    """
    Pull MMS IDs out of Analytics report rows.

    Args:
        rows: Rows from Analytics.fetch_report_rows (dicts keyed Column0, Column1, ...)
        report_path: Report path, for error messages

    Returns:
        Non-blank MMS IDs in report order

    Raises:
        ReportError: If the report has no rows, a row lacks the MMS ID
            column, or no row holds an MMS ID
    """
    if not rows:
        raise ReportError(f"Report returned no rows: {report_path}")

    missing = sum(1 for row in rows if MMS_ID_COLUMN not in row)
    if missing:
        raise ReportError(
            f"{missing} of {len(rows)} rows lack '{MMS_ID_COLUMN}' in report "
            f"{report_path}. The report structure may have changed."
        )

    mms_ids = [row[MMS_ID_COLUMN].strip() for row in rows if row[MMS_ID_COLUMN].strip()]
    if not mms_ids:
        raise ReportError(f"Report has rows but no MMS IDs: {report_path}")

    return mms_ids


class AlmaCollectionManager:
    """
    Manages one Alma Digital Collection using almaapitk.

    Provides functionality to:
    - Get collection members
    - Add/remove items from the collection
    - Synchronize the collection with Analytics reports
    """

    def __init__(
        self,
        client: AlmaAPIClient,
        collection_id: str,
        bibs: Optional[BibliographicRecords] = None,
        analytics: Optional[Analytics] = None,
    ):
        """
        Initialize the Alma Collection Manager.

        Args:
            client: AlmaAPIClient instance (configured for SANDBOX or PRODUCTION)
            collection_id: ID of the digital collection to manage
            bibs: BibliographicRecords domain (default: built from client)
            analytics: Analytics domain (default: built from client)
        """
        self.client = client
        self.collection_id = collection_id
        self.bibs = bibs or BibliographicRecords(client)
        self.analytics = analytics or Analytics(client)
        self.logger = client.logger

        self.logger.info(f"AlmaCollectionManager initialized for collection ID: {collection_id}")

    def get_collection_mms_ids(self) -> List[str]:
        """
        Get all MMS IDs currently in the collection.

        Returns:
            List of MMS IDs
        """
        response = self.bibs.get_collection_members(self.collection_id, limit=MEMBERS_PAGE_SIZE)
        data = response.json()
        total = data.get("total_record_count", 0)
        mms_ids = [bib["mms_id"] for bib in data.get("bib", [])]

        for offset in range(MEMBERS_PAGE_SIZE, total, MEMBERS_PAGE_SIZE):
            self.logger.debug(f"Getting MMS IDs batch with offset {offset}")
            response = self.bibs.get_collection_members(
                self.collection_id,
                limit=MEMBERS_PAGE_SIZE,
                offset=offset
            )
            mms_ids.extend(bib["mms_id"] for bib in response.json().get("bib", []))

        self.logger.info(f"Retrieved {len(mms_ids)} of {total} MMS IDs from collection")
        return mms_ids

    def add_to_collection(self, mms_ids: List[str]) -> None:
        """
        Add items to the collection.

        Args:
            mms_ids: List of MMS IDs to add
        """
        unique_mms_ids = sorted(set(mms_ids))
        self.logger.info(f"Adding {len(unique_mms_ids)} items to collection {self.collection_id}")

        success_count = 0
        error_count = 0

        for i, mms_id in enumerate(unique_mms_ids, 1):
            try:
                self.bibs.add_to_collection(self.collection_id, mms_id)
                success_count += 1
            except AlmaAPIError as e:
                # 400 may indicate already in collection - not a real error
                if e.status_code == 400 and "already assigned" in str(e).lower():
                    self.logger.debug(f"MMS ID {mms_id} already in collection")
                    success_count += 1
                else:
                    self.logger.warning(f"Failed to add MMS ID {mms_id}: {e}")
                    error_count += 1

            if i % 20 == 0 or i == len(unique_mms_ids):
                self.logger.debug(
                    f"Processed {i}/{len(unique_mms_ids)} additions. "
                    f"Success: {success_count}, Errors: {error_count}"
                )

        self.logger.info(f"Addition complete. Success: {success_count}, Errors: {error_count}")

    def remove_from_collection(self, mms_ids: List[str]) -> None:
        """
        Remove items from the collection.

        Args:
            mms_ids: List of MMS IDs to remove
        """
        unique_mms_ids = sorted(set(mms_ids))
        self.logger.info(f"Removing {len(unique_mms_ids)} items from collection {self.collection_id}")

        success_count = 0
        error_count = 0

        for i, mms_id in enumerate(unique_mms_ids, 1):
            try:
                self.bibs.remove_from_collection(self.collection_id, mms_id)
                success_count += 1
            except AlmaAPIError as e:
                # May fail if bib has representations - log and continue
                self.logger.warning(f"Failed to remove MMS ID {mms_id}: {e}")
                error_count += 1

            if i % 20 == 0 or i == len(unique_mms_ids):
                self.logger.debug(
                    f"Processed {i}/{len(unique_mms_ids)} removals. "
                    f"Success: {success_count}, Errors: {error_count}"
                )

        self.logger.info(f"Removal complete. Success: {success_count}, Errors: {error_count}")

    def get_mms_ids_from_report(self, report_path: str) -> List[str]:
        """
        Get MMS IDs from an Analytics report.

        Args:
            report_path: Path to the Analytics report

        Returns:
            List of MMS IDs from the report

        Raises:
            ReportError: If the report is empty or malformed
            AlmaAPIError: If the Analytics request fails
        """
        self.logger.info(f"Fetching MMS IDs from report: {report_path}")
        rows = self.analytics.fetch_report_rows(report_path)
        mms_ids = extract_mms_ids(rows, report_path)
        self.logger.info(f"Found {len(mms_ids)} MMS IDs in {len(rows)} report rows")
        return mms_ids

    def get_mms_ids_from_reports(self, report_paths: List[str]) -> List[str]:
        """
        Get unique MMS IDs from all reports. Any failed report fails the whole set.

        Args:
            report_paths: List of Analytics report paths

        Returns:
            Unique MMS IDs from all reports

        Raises:
            ReportError: If there are no report paths, or any report is empty or malformed
            AlmaAPIError: If any Analytics request fails
        """
        if not report_paths:
            raise ReportError("No report paths configured")

        report_mms_ids = set()
        for i, path in enumerate(report_paths, 1):
            self.logger.info(f"Processing report {i}/{len(report_paths)}: {path}")
            report_mms_ids.update(self.get_mms_ids_from_report(path))

        self.logger.info(f"Found {len(report_mms_ids)} unique MMS IDs from all reports.")
        return sorted(report_mms_ids)

    def update_collection_from_reports(self, report_paths: List[str]) -> Optional[SyncPlan]:
        """
        Synchronize collection with MMS IDs from Analytics reports.

        Process:
        1. Fetch all unique MMS IDs from reports (any empty/failed report → stop)
        2. Fetch current collection members
        3. Calculate differences (to add, to remove)
        4. Add new items, remove old items

        Args:
            report_paths: List of Analytics report paths

        Returns:
            The applied SyncPlan, or None if the collection was left untouched
        """
        self.logger.info(
            f"Starting synchronization for collection {self.collection_id} "
            f"using {len(report_paths)} report(s)."
        )

        # 1. Fetch all MMS IDs from reports; a bad report leaves the collection alone
        try:
            report_mms_ids = self.get_mms_ids_from_reports(report_paths)
        except ReportError as e:
            self.logger.warning(f"{e}. Collection will not be modified.")
            return None

        # 2. Fetch current collection state
        self.logger.info(f"Fetching current state of collection {self.collection_id}")
        current_mms_ids = self.get_collection_mms_ids()

        # 3. Calculate differences
        plan = plan_sync(report_mms_ids, current_mms_ids)
        self.logger.info(f"MMS IDs to add: {len(plan.to_add)}")
        self.logger.info(f"MMS IDs to remove: {len(plan.to_remove)}")

        # 4. Apply
        if plan.to_add:
            self.add_to_collection(plan.to_add)
        else:
            self.logger.info("No new items to add.")

        if plan.to_remove:
            self.remove_from_collection(plan.to_remove)
        else:
            self.logger.info("No items to remove.")

        self.logger.info(
            f"Collection {self.collection_id} synchronization completed successfully."
        )
        return plan


class ConfigManager:
    """
    Manages configuration from YAML files.
    """

    def __init__(self, config_file_path: str):
        """
        Initialize ConfigManager.

        Args:
            config_file_path: Path to YAML configuration file
        """
        self.config_file_path = config_file_path
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load and validate configuration from YAML file."""
        self.logger.info(f"Loading configuration from {self.config_file_path}")

        with open(self.config_file_path, 'r') as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("Configuration file is empty")

        if 'tasks' not in config:
            raise ValueError("Configuration must contain a 'tasks' section")

        for task_name, task_config in config['tasks'].items():
            if 'collection_id' not in task_config:
                raise ValueError(f"Task '{task_name}' missing 'collection_id'")
            if 'report_paths' not in task_config:
                raise ValueError(f"Task '{task_name}' missing 'report_paths'")
            if not isinstance(task_config['report_paths'], list):
                raise ValueError(f"Task '{task_name}': 'report_paths' must be a list")

        self.logger.info(f"Configuration loaded with {len(config['tasks'])} tasks")
        return config

    def get_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get all task configurations."""
        return self.config.get('tasks', {})

    def get_environment(self) -> str:
        """Get environment (SANDBOX or PRODUCTION)."""
        return self.config.get('environment', 'PRODUCTION')

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific task."""
        return self.config.get('tasks', {}).get(task_name)


def resolve_config_path(cli_config: Optional[str] = None) -> str:
    """Resolve configuration file path."""
    if cli_config:
        return cli_config

    if os.environ.get('ALMA_CONFIG_PATH'):
        return os.environ['ALMA_CONFIG_PATH']

    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'config.yml')


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Alma Digital Collection Sync')
    parser.add_argument(
        '--task', '-t', dest='tasks', action='append',
        help='Specific task(s) to run. If omitted, all tasks run.'
    )
    parser.add_argument(
        '--config', '-c', default=None,
        help='Path to configuration file'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--log-dir', default='logs',
        help='Directory for log files (default: ./logs)'
    )
    args = parser.parse_args()

    # Setup logging — console + timestamped file (matches v5 CLI behavior)
    log_dir = os.path.abspath(args.log_dir)
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"alma_manager_{timestamp}.log")

    # Build handlers explicitly so we can also attach the file handler to
    # almaapitk's per-domain loggers (they have propagate=False, so root's
    # handlers don't see their messages by default).
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)  # filter DEBUG noise from almaapitk; full DEBUG stays in almaapitk's own per-domain logs

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

    # Capture almaapitk's API/domain log messages in our archive log file too
    for almapi_name in ('almapi.api_client', 'almapi.bibs', 'almapi.admin'):
        logging.getLogger(almapi_name).addHandler(file_handler)

    logger = logging.getLogger(__name__)
    logger.info(f"Logging to: {log_file}")

    try:
        logger.info("Starting Alma Digital Collection Sync (almaapitk)")

        # Load configuration
        config_path = resolve_config_path(args.config)
        logger.info(f"Using configuration: {config_path}")
        config_manager = ConfigManager(config_path)

        # Get environment
        environment = config_manager.get_environment()
        logger.info(f"Environment: {environment}")

        # Create AlmaAPIClient
        client = AlmaAPIClient(environment)

        # Get tasks
        all_tasks = config_manager.get_tasks()

        # Determine which tasks to run
        if args.tasks:
            tasks_to_run = {
                name: all_tasks[name]
                for name in args.tasks
                if name in all_tasks
            }
            if not tasks_to_run:
                raise ValueError("None of the specified tasks found in configuration")
        else:
            tasks_to_run = all_tasks

        logger.info(f"Running {len(tasks_to_run)} task(s)")

        # Process tasks
        for task_name, task_config in tasks_to_run.items():
            logger.info(f"Starting task: {task_name}")

            collection_id = task_config['collection_id']
            report_paths = task_config['report_paths']

            if args.dry_run:
                logger.info(f"[DRY-RUN] Would sync collection {collection_id}")
                logger.info(f"[DRY-RUN] Report paths: {report_paths}")
                continue

            # Create manager and sync
            manager = AlmaCollectionManager(client, collection_id)
            manager.update_collection_from_reports(report_paths)

            logger.info(f"Task '{task_name}' completed")

        logger.info("All tasks completed successfully")

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        exit(1)
    except AlmaAPIError as e:
        logger.error(f"Alma API error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
