#!/usr/bin/env python3
"""
Dry Test for AlmaCollectionManager v6

Fetches real data from Alma sandbox and reports what changes would be made
without actually executing add/remove operations.

Usage:
    python dry_test.py --collection-id <ID> [--report-path <PATH>]
    python dry_test.py --config config.yml --task <TASK_NAME>
"""

import os
import sys
import argparse
import logging
from typing import List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from AlmaCollectionManager_6 import AlmaCollectionManager, ConfigManager
from almaapitk import AlmaAPIClient


def setup_logging():
    """Setup logging for dry test."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def run_dry_test(
    client: AlmaAPIClient,
    collection_id: str,
    report_paths: Optional[List[str]] = None,
    logger: logging.Logger = None
):
    """
    Run dry test: fetch data and report diffs without making changes.

    Args:
        client: AlmaAPIClient instance
        collection_id: Digital collection ID
        report_paths: Optional list of Analytics report paths
        logger: Logger instance
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    print("\n" + "="*70)
    print("DRY TEST - AlmaCollectionManager v6")
    print("="*70)
    print(f"Environment: {client.environment}")
    print(f"Collection ID: {collection_id}")
    print("="*70 + "\n")

    # Create manager
    manager = AlmaCollectionManager(client, collection_id)

    # Step 1: Fetch current collection state
    print("[1/4] Fetching current collection state...")
    try:
        current_count = manager.get_collection_count()
        print(f"      Collection contains {current_count} items")

        current_mms_ids = []
        if current_count > 0:
            current_mms_ids = manager.get_collection_mms_ids(current_count)
            print(f"      Retrieved {len(current_mms_ids)} MMS IDs from collection")

            # Show sample of current items
            if current_mms_ids:
                print(f"      Sample (first 5): {current_mms_ids[:5]}")
        else:
            print("      Collection is empty")
    except Exception as e:
        print(f"      ERROR fetching collection: {e}")
        return

    # Step 2: Fetch report data (if report paths provided)
    report_mms_ids = []
    if report_paths:
        print(f"\n[2/4] Fetching MMS IDs from {len(report_paths)} report(s)...")
        for i, path in enumerate(report_paths, 1):
            print(f"      Processing report {i}: {path}")
            try:
                ids = manager.get_mms_ids_from_report(path)
                report_mms_ids.extend(ids)
                print(f"      Found {len(ids)} MMS IDs in report {i}")
            except Exception as e:
                print(f"      ERROR fetching report: {e}")
                # Continue with other reports

        # Deduplicate
        report_mms_ids = list(set(report_mms_ids))
        print(f"      Total unique MMS IDs from reports: {len(report_mms_ids)}")

        if report_mms_ids:
            print(f"      Sample (first 5): {report_mms_ids[:5]}")
    else:
        print("\n[2/4] No report paths provided - skipping report fetch")
        print("      (Use --report-path to specify Analytics reports)")

    # Step 3: Calculate diffs
    print("\n[3/4] Calculating differences...")

    current_set = set(current_mms_ids)
    report_set = set(report_mms_ids)

    to_add = list(report_set - current_set)
    to_remove = list(current_set - report_set)
    unchanged = list(current_set & report_set)

    print(f"      Items to ADD:    {len(to_add)}")
    print(f"      Items to REMOVE: {len(to_remove)}")
    print(f"      Items unchanged: {len(unchanged)}")

    # Step 4: Report what would be done
    print("\n[4/4] DRY RUN REPORT - What would be done:")
    print("-"*50)

    if not report_paths:
        print("      No report paths provided - cannot calculate sync actions")
        print("      Provide --report-path to see what would be synced")
    elif not report_mms_ids:
        print("      No MMS IDs found in reports")
        print("      If reports are empty, no changes would be made")
    else:
        if to_add:
            print(f"\n      Would ADD {len(to_add)} items:")
            for mms_id in to_add[:10]:
                print(f"        + {mms_id}")
            if len(to_add) > 10:
                print(f"        ... and {len(to_add) - 10} more")
        else:
            print("\n      No items to add")

        if to_remove:
            print(f"\n      Would REMOVE {len(to_remove)} items:")
            for mms_id in to_remove[:10]:
                print(f"        - {mms_id}")
            if len(to_remove) > 10:
                print(f"        ... and {len(to_remove) - 10} more")
        else:
            print("\n      No items to remove")

    print("\n" + "="*70)
    print("DRY TEST COMPLETE - No changes were made")
    print("="*70 + "\n")

    return {
        'collection_count': current_count,
        'current_mms_ids': current_mms_ids,
        'report_mms_ids': report_mms_ids,
        'to_add': to_add,
        'to_remove': to_remove,
        'unchanged': unchanged
    }


def main():
    parser = argparse.ArgumentParser(
        description='Dry test for AlmaCollectionManager v6'
    )
    parser.add_argument(
        '--collection-id', '-i',
        help='Digital collection ID to test'
    )
    parser.add_argument(
        '--report-path', '-r',
        action='append',
        dest='report_paths',
        help='Analytics report path(s) to fetch (can specify multiple)'
    )
    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--task', '-t',
        help='Task name from config file'
    )
    parser.add_argument(
        '--environment', '-e',
        choices=['SANDBOX', 'PRODUCTION'],
        default='SANDBOX',
        help='Environment (default: SANDBOX)'
    )
    args = parser.parse_args()

    logger = setup_logging()

    # Determine collection ID and report paths
    collection_id = args.collection_id
    report_paths = args.report_paths or []
    environment = args.environment

    if args.config:
        # Load from config file
        config_manager = ConfigManager(args.config)
        environment = config_manager.get_environment()

        if args.task:
            task_config = config_manager.get_task(args.task)
            if not task_config:
                logger.error(f"Task '{args.task}' not found in config")
                sys.exit(1)
            collection_id = task_config['collection_id']
            report_paths = task_config.get('report_paths', [])
        else:
            # Use first task
            tasks = config_manager.get_tasks()
            if tasks:
                first_task = list(tasks.values())[0]
                collection_id = first_task['collection_id']
                report_paths = first_task.get('report_paths', [])

    if not collection_id:
        logger.error("Collection ID required. Use --collection-id or --config")
        sys.exit(1)

    # Create client
    logger.info(f"Connecting to Alma {environment}...")
    client = AlmaAPIClient(environment)

    # Run dry test
    run_dry_test(client, collection_id, report_paths, logger)


if __name__ == "__main__":
    main()
