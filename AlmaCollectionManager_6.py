#!/usr/bin/env python3
"""
Alma Digital Collection Manager v6

Manages Alma Digital Collections using the almaapitk library.
Synchronizes collections with MMS IDs from Analytics reports.

Changes from v5:
- Uses almaapitk.BibliographicRecords for collection operations
- Uses almaapitk.AlmaAPIClient for API communication
- Uses almaapitk logging infrastructure
- Cleaner error handling via AlmaAPIError

Dependencies:
- almaapitk (pip install almaapitk)
- pyyaml
- beautifulsoup4
- lxml
"""

import os
import yaml
import argparse
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from almaapitk import AlmaAPIClient, BibliographicRecords, AlmaAPIError


class AlmaCollectionManager:
    """
    Manages Alma Digital Collections using almaapitk.

    Provides functionality to:
    - Get collection members and count
    - Add/remove items from collections
    - Synchronize collections with Analytics reports
    """

    def __init__(self, client: AlmaAPIClient, collection_id: str):
        """
        Initialize the Alma Collection Manager.

        Args:
            client: AlmaAPIClient instance (configured for SANDBOX or PRODUCTION)
            collection_id: ID of the digital collection to manage
        """
        self.client = client
        self.collection_id = collection_id
        self.bibs = BibliographicRecords(client)
        self.logger = client.logger

        self.logger.info(f"AlmaCollectionManager initialized for collection ID: {collection_id}")

    def get_collection_count(self) -> int:
        """
        Get the count of items in the collection.

        Returns:
            Number of items in the collection
        """
        self.logger.debug(f"Getting count for collection {self.collection_id}")

        response = self.bibs.get_collection_members(self.collection_id, limit=1)
        data = response.json()
        count = data.get("total_record_count", 0)

        self.logger.debug(f"Collection count: {count}")
        return count

    def get_collection_mms_ids(self, count: int) -> List[str]:
        """
        Get all MMS IDs currently in the collection.

        Args:
            count: Total number of items in the collection

        Returns:
            List of MMS IDs
        """
        mms_ids = []
        self.logger.debug(f"Retrieving {count} MMS IDs from collection")

        for offset in range(0, count, 100):
            self.logger.debug(f"Getting MMS IDs batch with offset {offset}")

            response = self.bibs.get_collection_members(
                self.collection_id,
                limit=100,
                offset=offset
            )
            data = response.json()

            batch_ids = [bib["mms_id"] for bib in data.get("bib", [])]
            mms_ids.extend(batch_ids)
            self.logger.debug(f"Retrieved {len(batch_ids)} MMS IDs in this batch")

        self.logger.info(f"Retrieved {len(mms_ids)} total MMS IDs from collection")
        return mms_ids

    def add_to_collection(self, mms_ids: List[str]) -> None:
        """
        Add items to the collection.

        Args:
            mms_ids: List of MMS IDs to add
        """
        if not mms_ids:
            self.logger.warning("No MMS IDs provided to add to collection")
            return

        # Deduplicate
        unique_mms_ids = list(set(mms_ids))
        if len(unique_mms_ids) < len(mms_ids):
            self.logger.info(
                f"Removed {len(mms_ids) - len(unique_mms_ids)} duplicate MMS IDs"
            )

        self.logger.info(f"Adding {len(unique_mms_ids)} items to collection {self.collection_id}")

        success_count = 0
        error_count = 0

        for i, mms_id in enumerate(unique_mms_ids, 1):
            try:
                self.bibs.add_to_collection(self.collection_id, mms_id)
                success_count += 1

                if i % 20 == 0 or i == len(unique_mms_ids):
                    self.logger.debug(
                        f"Processed {i}/{len(unique_mms_ids)} additions. "
                        f"Success: {success_count}, Errors: {error_count}"
                    )

            except AlmaAPIError as e:
                # 400 may indicate already in collection - not a real error
                if e.status_code == 400 and "already assigned" in str(e).lower():
                    self.logger.debug(f"MMS ID {mms_id} already in collection")
                    success_count += 1
                else:
                    self.logger.warning(f"Failed to add MMS ID {mms_id}: {e}")
                    error_count += 1

        self.logger.info(f"Addition complete. Success: {success_count}, Errors: {error_count}")

    def remove_from_collection(self, mms_ids: List[str]) -> None:
        """
        Remove items from the collection.

        Args:
            mms_ids: List of MMS IDs to remove
        """
        if not mms_ids:
            self.logger.warning("No MMS IDs provided to remove from collection")
            return

        # Deduplicate
        unique_mms_ids = list(set(mms_ids))
        if len(unique_mms_ids) < len(mms_ids):
            self.logger.info(
                f"Removed {len(mms_ids) - len(unique_mms_ids)} duplicate MMS IDs"
            )

        self.logger.info(f"Removing {len(unique_mms_ids)} items from collection {self.collection_id}")

        success_count = 0
        error_count = 0

        for i, mms_id in enumerate(unique_mms_ids, 1):
            try:
                self.bibs.remove_from_collection(self.collection_id, mms_id)
                success_count += 1

                if i % 20 == 0 or i == len(unique_mms_ids):
                    self.logger.debug(
                        f"Processed {i}/{len(unique_mms_ids)} removals. "
                        f"Success: {success_count}, Errors: {error_count}"
                    )

            except AlmaAPIError as e:
                # May fail if bib has representations - log and continue
                self.logger.warning(f"Failed to remove MMS ID {mms_id}: {e}")
                error_count += 1

        self.logger.info(f"Removal complete. Success: {success_count}, Errors: {error_count}")

    def get_mms_ids_from_report(self, report_path: str, limit: int = 100) -> List[str]:
        """
        Get MMS IDs from an Analytics report with pagination.

        Note: Analytics API is not yet in almaapitk, using direct requests.

        Args:
            report_path: Path to the Analytics report
            limit: Results per request (must be multiple of 25, max 1000)

        Returns:
            List of MMS IDs from the report
        """
        self.logger.info(f"Fetching MMS IDs from report: {report_path}")
        mms_ids = []
        token = None
        page = 1

        # Use the client's base URL and API key
        base_url = self.client.base_url.rstrip('/')
        headers = {"Accept": "application/xml"}

        while True:
            params = {
                'path': report_path,
                'limit': limit,
                'col_names': 'false',
                'apikey': self.client.api_key
            }

            if token:
                params['token'] = token

            self.logger.debug(f"Fetching page {page} of report data")

            response = requests.get(
                f'{base_url}/almaws/v1/analytics/reports',
                params=params,
                headers=headers
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "lxml-xml")

            # Find MMS IDs in Column1
            raw_mms_elements = soup.find_all('Column1')

            if not raw_mms_elements:
                self.logger.warning(
                    f"No 'Column1' elements found on page {page}. "
                    "Report may be empty or structure changed."
                )

            page_mms_ids = [element.get_text() for element in raw_mms_elements]
            mms_ids.extend(page_mms_ids)

            self.logger.info(f"Found {len(page_mms_ids)} MMS IDs on page {page}")

            # Check for more pages
            resumption_token = soup.find('ResumptionToken')
            is_finished = soup.find('IsFinished')

            if (not resumption_token or
                not resumption_token.text or
                (is_finished and is_finished.text.lower() == 'true')):
                break

            token = resumption_token.text
            page += 1

        self.logger.info(
            f"Completed fetching report data. "
            f"Total pages: {page}, Total MMS IDs: {len(mms_ids)}"
        )
        return mms_ids

    def update_collection_from_reports(self, report_paths: List[str]) -> None:
        """
        Synchronize collection with MMS IDs from Analytics reports.

        Process:
        1. Fetch all unique MMS IDs from reports
        2. Fetch current collection members
        3. Calculate differences (to add, to remove)
        4. Add new items, remove old items

        Args:
            report_paths: List of Analytics report paths
        """
        self.logger.info(
            f"Starting synchronization for collection {self.collection_id} "
            f"using {len(report_paths)} report(s)."
        )

        # 1. Fetch all MMS IDs from reports
        report_mms_ids = []
        for i, path in enumerate(report_paths, 1):
            self.logger.info(f"Processing report {i}/{len(report_paths)}: {path}")
            mms_ids_from_report = self.get_mms_ids_from_report(path)
            report_mms_ids.extend(mms_ids_from_report)
            self.logger.info(f"Found {len(mms_ids_from_report)} items in report {i}")

        # Deduplicate
        report_mms_ids = list(set(report_mms_ids))
        self.logger.info(f"Found {len(report_mms_ids)} unique MMS IDs from all reports.")

        # 2. If empty, skip
        if not report_mms_ids:
            self.logger.info(
                "No items found in reports. Collection will not be modified."
            )
            return

        # 3. Fetch current collection state
        self.logger.info(f"Fetching current state of collection {self.collection_id}")
        current_count = self.get_collection_count()
        current_mms_ids = []
        if current_count > 0:
            current_mms_ids = self.get_collection_mms_ids(current_count)
        self.logger.info(
            f"Collection {self.collection_id} currently contains {len(current_mms_ids)} items."
        )

        # 4. Calculate differences
        report_set = set(report_mms_ids)
        current_set = set(current_mms_ids)

        mms_ids_to_add = list(report_set - current_set)
        mms_ids_to_remove = list(current_set - report_set)

        self.logger.info(f"MMS IDs to add: {len(mms_ids_to_add)}")
        self.logger.info(f"MMS IDs to remove: {len(mms_ids_to_remove)}")

        # 5. Add new items
        if mms_ids_to_add:
            self.logger.info(f"Adding {len(mms_ids_to_add)} items to collection")
            self.add_to_collection(mms_ids_to_add)
        else:
            self.logger.info("No new items to add.")

        # 6. Remove old items
        if mms_ids_to_remove:
            self.logger.info(f"Removing {len(mms_ids_to_remove)} items from collection")
            self.remove_from_collection(mms_ids_to_remove)
        else:
            self.logger.info("No items to remove.")

        self.logger.info(
            f"Collection {self.collection_id} synchronization completed successfully."
        )


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
    parser = argparse.ArgumentParser(description='Alma Digital Collection Manager v6')
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
    args = parser.parse_args()

    # Setup basic logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting Alma Digital Collection Manager v6 (almaapitk)")

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
