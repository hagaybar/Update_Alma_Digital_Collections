import requests
import json
import pandas as pd
from bs4 import BeautifulSoup
import os
import yaml
import argparse
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime


class Logger:
    """
    Class to handle logging functionality for the Alma Collection Manager.
    
    Creates and manages logs in both file and console formats.
    """
    
    def __init__(self, log_level: str = "INFO", log_dir: str = "logs"):
        """
        Initialize the logger.
        
        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_dir: Directory to store log files
        """
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        # Make log_dir absolute (so it won't depend on CWD)
        self.log_dir = os.path.abspath(log_dir)
        # self.log_dir = log_dir
        
        # Create logs directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
                    
        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, f"alma_manager_{timestamp}.log")
        
        # Configure logging
        self.setup_logger()
        
    def setup_logger(self) -> None:
        """
        Configure the logger with file and console handlers.
        """
        # Create logger
        logger = logging.getLogger()
        logger.setLevel(self.log_level)
        
        # Clear any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create file handler
        file_handler = logging.FileHandler(self.log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # Log the initialization
        logging.info(f"Logger initialized. Log file: {self.log_file}")


class AlmaCollectionManager:
    """
    A class to manage collections in the Alma library system.
    
    This class provides functionality to:
    - Clear specified collections
    - Retrieve MMS IDs from Analytics reports
    - Add items to collections based on MMS IDs
    - Synchronize collections with Analytics reports
    """
    
    def __init__(self, api_key: str, collection_id: str, region: str = "na"):
        """
        Initialize the Alma Collection Manager.
        
        Args:
            api_key: API key with Bib Read/Write and Analytics permissions
            collection_id: ID of the collection to manage
            region: Alma region code (default: "na" for North America)
        """
        self.alma_base = f'https://api-{region}.hosted.exlibrisgroup.com/almaws/v1'
        self.api_key = api_key
        self.collection_id = collection_id
        self.headers_json = {"Accept": "application/json"}
        self.headers_xml = {"Accept": "application/xml"}
        
        # Get logger
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"AlmaCollectionManager initialized for collection ID: {collection_id}")
        self.logger.debug(f"Using API base URL: {self.alma_base}")
        
    def get_collection_count(self) -> int:
        """
        Get the count of items in the specified collection.
        
        Returns:
            int: Number of items in the collection
        """
        self.logger.debug(f"Getting count for collection {self.collection_id}")
        
        try:
            response = requests.get(
                f'{self.alma_base}/bibs/collections/{self.collection_id}/bibs',
                params={'apikey': self.api_key, 'limit': 1},
                headers=self.headers_json
            ).json()
            
            count = response["total_record_count"]
            self.logger.debug(f"Collection count: {count}")
            return count
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get collection count: {str(e)}")
            raise
        except KeyError as e:
            self.logger.error(f"Invalid response format from Alma API: {str(e)}")
            raise ValueError(f"Invalid response from Alma API: {response}")
    
    def get_collection_mms_ids(self, count: int) -> List[str]:
        """
        Get all MMS IDs currently in the collection.
        
        Args:
            count: Total number of items in the collection
            
        Returns:
            List[str]: List of MMS IDs
        """
        mms_ids = []
        self.logger.debug(f"Retrieving {count} MMS IDs from collection")
        
        try:
            for offset in range(0, count, 100):
                self.logger.debug(f"Getting MMS IDs batch with offset {offset}")
                response = requests.get(
                    f'{self.alma_base}/bibs/collections/{self.collection_id}/bibs',
                    params={'apikey': self.api_key, 'limit': 100, 'offset': offset},
                    headers=self.headers_json
                ).json()
                
                batch_ids = [bib["mms_id"] for bib in response.get("bib", [])]
                mms_ids.extend(batch_ids)
                self.logger.debug(f"Retrieved {len(batch_ids)} MMS IDs in this batch")
                
            self.logger.info(f"Retrieved {len(mms_ids)} total MMS IDs from collection")
            return mms_ids
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to get collection MMS IDs: {str(e)}")
            raise
        except KeyError as e:
            self.logger.error(f"Invalid response format from Alma API: {str(e)}")
            raise ValueError(f"Invalid response structure from Alma API")
    
    def clear_collection(self) -> None:
        """
        Remove all items from the specified collection.
        """
        self.logger.info(f"Clearing collection {self.collection_id}")
        
        try:
            count = self.get_collection_count()
            self.logger.info(f"Current collection contains {count} items")
            
            if count > 0:
                mms_ids = self.get_collection_mms_ids(count)
                
                self.logger.info(f"Removing {len(mms_ids)} items from collection")
                
                for i, mms_id in enumerate(mms_ids, 1):
                    try:
                        response = requests.delete(
                            f'{self.alma_base}/bibs/collections/{self.collection_id}/bibs/{mms_id}',
                            params={'apikey': self.api_key}
                        )
                        response.raise_for_status()
                        
                        # Log progress periodically
                        if i % 20 == 0 or i == len(mms_ids):
                            self.logger.debug(f"Removed {i}/{len(mms_ids)} items")
                            
                    except requests.exceptions.RequestException as e:
                        self.logger.warning(f"Failed to remove MMS ID {mms_id}: {str(e)}")
                        # Continue with other IDs even if one fails
                        
                self.logger.info(f"Completed removing items from collection")
            else:
                self.logger.info("Collection is already empty")
                
        except Exception as e:
            self.logger.error(f"Error clearing collection: {str(e)}")
            raise


    def get_mms_ids_from_report(self, report_path: str, limit: int = 100) -> List[str]:
        """
        Get MMS IDs from an Analytics report, handling pagination with resumption tokens.
        
        Args:
            report_path: Path to the Analytics report
            limit: Maximum number of results per request (must be multiple of 25, max 1000)
            
        Returns:
            List[str]: Complete list of MMS IDs from the report
        """
        self.logger.info(f"Fetching MMS IDs from report: {report_path}")
        mms_ids = []
        token = None
        page = 1
        
        try:
            while True:
                # Prepare parameters for the request
                params = {
                    'path': report_path,
                    'limit': limit,
                    'col_names': 'false',
                    'apikey': self.api_key
                }
                
                # Add token if we have one from a previous request
                if token:
                    params['token'] = token
                    
                self.logger.debug(f"Fetching page {page} of report data")
                
                # Make the request
                response = requests.get(
                    f'{self.alma_base}/analytics/reports',
                    params=params,
                    headers=self.headers_xml
                )
                
                response.raise_for_status()
                
                # Parse returned XML data with Beautiful Soup
                soup = BeautifulSoup(response.content, "lxml-xml")
                
                # Find the MMS IDs in the report output
                raw_mms_elements = soup.find_all('Column1')
                
                if not raw_mms_elements:
                    self.logger.warning(f"No 'Column1' elements found on page {page}. Report may be empty or structure changed.")
                
                # Add MMS IDs from this page to our list
                page_mms_ids = [element.get_text() for element in raw_mms_elements]
                mms_ids.extend(page_mms_ids)
                
                self.logger.info(f"Found {len(page_mms_ids)} MMS IDs on page {page}")
                
                # Look for resumption token
                resumption_token = soup.find('ResumptionToken')
                is_finished = soup.find('IsFinished')
                
                # Check if we're done or if we need to fetch another page
                if (not resumption_token or 
                    not resumption_token.text or 
                    (is_finished and is_finished.text.lower() == 'true')):
                    break
                    
                # Update token for next request
                token = resumption_token.text
                page += 1
            
            self.logger.info(f"Completed fetching report data. Total pages: {page}, Total MMS IDs: {len(mms_ids)}")
            return mms_ids
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to retrieve report: {str(e)}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing report data: {str(e)}")
            raise


    def add_to_collection(self, mms_ids: List[str]) -> None:
        """
        Add items to the collection based on their MMS IDs.
        
        Args:
            mms_ids: List of MMS IDs to add to the collection
        """
        if not mms_ids:
            self.logger.warning("No MMS IDs provided to add to collection")
            return
            
        self.logger.info(f"Adding {len(mms_ids)} items to collection {self.collection_id}")
            # Deduplicate MMS IDs to avoid duplicate API calls
        unique_mms_ids = list(set(mms_ids))
        # Log deduplication info
        if len(unique_mms_ids) < len(mms_ids):
            self.logger.info(f"Removed {len(mms_ids) - len(unique_mms_ids)} duplicate MMS IDs from the add list during deduplication")

        success_count = 0
        error_count = 0
        
        for i, mms_id in enumerate(unique_mms_ids, 1):
            request_body = {
                "link": "",
                "mms_id": mms_id,
                "record_format": "marc21",
                "suppress_from_publishing": "false",
                "suppress_from_external_search": "false",
                "suppress_from_metadoor": "false",
                "sync_with_oclc": "BIBS",
                "sync_with_libraries_australia": "NONE",
                "cataloging_level": {
                    "value": "00"
                },
                "brief_level": {
                    "value": "01"
                }
            }
            
            try:
                response = requests.post(
                    f'{self.alma_base}/bibs/collections/{self.collection_id}/bibs',
                    params={'apikey': self.api_key},
                    headers=self.headers_json,
                    json=request_body
                )
                response.raise_for_status()
                success_count += 1
                
                # Log progress periodically
                if i % 20 == 0 or i == len(unique_mms_ids):
                    self.logger.debug(f"Processed {i}/{len(unique_mms_ids)} additions. Current success: {success_count}, errors: {error_count}")
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Failed to add MMS ID {mms_id}: {str(e)}")
                error_count += 1
                # Continue with other IDs even if one fails
                
        self.logger.info(f"Addition complete. Success: {success_count}, Errors: {error_count}")

    def remove_from_collection(self, mms_ids: List[str]) -> None:
        """
        Remove items from the collection based on their MMS IDs.

        Args:
            mms_ids: List of MMS IDs to remove from the collection
        """
        if not mms_ids:
            self.logger.warning("No MMS IDs provided to remove from collection")
            return

        self.logger.info(f"Removing {len(mms_ids)} items from collection {self.collection_id}")
        
        # Deduplicate MMS IDs to avoid issues, though API should handle it
        unique_mms_ids = list(set(mms_ids))
        if len(unique_mms_ids) < len(mms_ids):
             self.logger.info(f"Removed {len(mms_ids) - len(unique_mms_ids)} duplicate MMS IDs from removal list")

        success_count = 0
        error_count = 0

        for i, mms_id in enumerate(unique_mms_ids, 1):
            try:
                response = requests.delete(
                    f'{self.alma_base}/bibs/collections/{self.collection_id}/bibs/{mms_id}',
                    params={'apikey': self.api_key}
                )
                response.raise_for_status()  # Check for HTTP errors
                success_count += 1

                # Log progress periodically
                if i % 20 == 0 or i == len(unique_mms_ids):
                    self.logger.debug(f"Processed {i}/{len(unique_mms_ids)} removal requests. Success: {success_count}, Errors: {error_count}")

            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Failed to remove MMS ID {mms_id}: {str(e)}")
                error_count += 1
                # Continue with other IDs even if one fails
        
        self.logger.info(f"Removal complete. Success: {success_count}, Errors: {error_count}")
    
    def update_collection_from_reports(self, report_paths: List[str]) -> None:
        """
        Synchronizes the items in the specified Alma collection with the MMS IDs found
        in one or more Analytics reports.

        The process involves:
        1. Fetching all unique MMS IDs from the provided Analytics report(s).
        2. Fetching all MMS IDs currently in the target Alma collection.
        3. Calculating the differences:
            - MMS IDs in the report(s) but not in the collection (to be added).
            - MMS IDs in the collection but not in the report(s) (to be removed).
        4. Adding the new MMS IDs to the collection.
        5. Removing the outdated MMS IDs from the collection.

        If no MMS IDs are found in any of the reports, the collection remains unmodified.

        Args:
            report_paths: A list of strings, where each string is the path to an
                          Analytics report containing MMS IDs.
        """
        self.logger.info(f"Starting synchronization for collection {self.collection_id} using {len(report_paths)} report(s).")

        try:
            # 1. Fetch all MMS IDs from the reports
            report_mms_ids = []
            for i, path in enumerate(report_paths, 1):
                self.logger.info(f"Processing report {i}/{len(report_paths)}: {path}")
                mms_ids_from_one_report = self.get_mms_ids_from_report(path)
                report_mms_ids.extend(mms_ids_from_one_report)
                self.logger.info(f"Found {len(mms_ids_from_one_report)} items in report {i}")
            
            # Deduplicate report_mms_ids
            report_mms_ids = list(set(report_mms_ids))
            self.logger.info(f"Found a total of {len(report_mms_ids)} unique MMS IDs from all reports.")

            # 2. If report_mms_ids is empty, log and skip
            if not report_mms_ids:
                self.logger.info("No items found in any of the reports. Collection will not be modified.")
                return

            # 3. Fetch all MMS IDs currently in the Alma collection
            self.logger.info(f"Fetching current state of collection {self.collection_id}")
            current_collection_count = self.get_collection_count()
            current_collection_mms_ids = []
            if current_collection_count > 0:
                current_collection_mms_ids = self.get_collection_mms_ids(current_collection_count)
            self.logger.info(f"Collection {self.collection_id} currently contains {len(current_collection_mms_ids)} items.")

            # 4. Calculate differences
            report_mms_ids_set = set(report_mms_ids)
            current_collection_mms_ids_set = set(current_collection_mms_ids)

            mms_ids_to_add = list(report_mms_ids_set - current_collection_mms_ids_set)
            mms_ids_to_remove = list(current_collection_mms_ids_set - report_mms_ids_set)

            # 5. Log the counts
            self.logger.info(f"MMS IDs to add: {len(mms_ids_to_add)}")
            self.logger.info(f"MMS IDs to remove: {len(mms_ids_to_remove)}")

            # 6. Add new MMS IDs to the collection
            if mms_ids_to_add:
                self.logger.info(f"Adding {len(mms_ids_to_add)} items to collection {self.collection_id}")
                self.add_to_collection(mms_ids_to_add)
            else:
                self.logger.info("No new items to add to the collection.")

            # 7. Remove old MMS IDs from the collection
            if mms_ids_to_remove:
                self.logger.info(f"Removing {len(mms_ids_to_remove)} items from collection {self.collection_id}")
                self.remove_from_collection(mms_ids_to_remove)
            else:
                self.logger.info("No items to remove from the collection.")
            
            self.logger.info(f"Collection {self.collection_id} synchronization completed successfully.")

        except Exception as e:
            self.logger.error(f"Error during synchronization of collection {self.collection_id} from reports: {str(e)}")
            raise


class ConfigManager:
    """
    Class to manage configuration for Alma Collection Manager tasks.
    
    Handles loading and validating configuration from YAML files.
    """
    
    def __init__(self, config_file_path: str):
        """
        Initialize the ConfigManager.
        
        Args:
            config_file_path: Path to the YAML configuration file
        """
        self.config_file_path = config_file_path
        self.logger = logging.getLogger(__name__)
        self.logger.debug(f"Initializing ConfigManager with file: {config_file_path}")
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Returns:
            Dict: Configuration dictionary
        
        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If configuration is invalid
        """
        self.logger.info(f"Loading configuration from {self.config_file_path}")
        
        try:
            with open(self.config_file_path, 'r') as config_file:
                config = yaml.safe_load(config_file)
                
            if not config:
                self.logger.error("Configuration file is empty")
                raise ValueError("Configuration file is empty")
                
            # Validate configuration structure
            if 'tasks' not in config:
                self.logger.error("Configuration must contain a 'tasks' section")
                raise ValueError("Configuration must contain a 'tasks' section")
                
            for task_name, task_config in config['tasks'].items():
                if 'collection_id' not in task_config:
                    self.logger.error(f"Task '{task_name}' is missing required 'collection_id' field")
                    raise ValueError(f"Task '{task_name}' is missing required 'collection_id' field")
                if 'report_paths' not in task_config:
                    self.logger.error(f"Task '{task_name}' is missing required 'report_paths' field")
                    raise ValueError(f"Task '{task_name}' is missing required 'report_paths' field")
                if not isinstance(task_config['report_paths'], list):
                    self.logger.error(f"Task '{task_name}': 'report_paths' must be a list")
                    raise ValueError(f"Task '{task_name}': 'report_paths' must be a list")
            
            self.logger.info(f"Configuration loaded successfully with {len(config.get('tasks', {}))} tasks")
            return config
            
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {self.config_file_path}")
            raise FileNotFoundError(f"Configuration file not found: {self.config_file_path}")
        except yaml.YAMLError as e:
            self.logger.error(f"Invalid YAML in configuration file: {e}")
            raise ValueError(f"Invalid YAML in configuration file: {e}")
            
    def get_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all defined tasks from the configuration.
        
        Returns:
            Dict: Dictionary of task configurations
        """
        tasks = self.config.get('tasks', {})
        self.logger.debug(f"Retrieved {len(tasks)} tasks from configuration")
        return tasks
        
    def get_region(self) -> str:
        """
        Get the Alma region from the configuration.
        
        Returns:
            str: Alma region code (defaults to "na" if not specified)
        """
        region = self.config.get('region', 'na')
        self.logger.debug(f"Using Alma region: {region}")
        return region
        
    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific task.
        
        Args:
            task_name: Name of the task to retrieve
            
        Returns:
            Dict or None: Task configuration or None if not found
        """
        task = self.config.get('tasks', {}).get(task_name)
        if task:
            self.logger.debug(f"Retrieved configuration for task: {task_name}")
        else:
            self.logger.debug(f"Task not found in configuration: {task_name}")
        return task



def resolve_config_path(cli_config: str | None = None) -> str:
    if cli_config:
        return cli_config

    if os.environ.get('ALMA_CONFIG_PATH'):
        return os.environ['ALMA_CONFIG_PATH']

    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'config.yml')


def main():
    """
    Main entry point for the Alma Collection Manager.
    
    Loads configuration, creates manager instances, and executes tasks.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Alma Collection Manager')
    parser.add_argument('--task', '-t', dest='tasks', action='append',
                      help='Specific task(s) to run. Can be specified multiple times. If omitted, all tasks will run.')
    parser.add_argument('--log-level', '-l', default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Set the logging level')
    parser.add_argument('--log-dir', '-d', default='logs',
                      help='Directory to store log files')
    parser.add_argument('--config', '-c', default=None,
                      help='Path to configuration file (overrides ALMA_CONFIG_PATH environment variable)')
    args = parser.parse_args()
    
    # Initialize logger
    logger_instance = Logger(log_level=args.log_level, log_dir=args.log_dir)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting Alma Collection Manager")
        
        # Get API key from environment variable
        api_key = os.environ.get('ALMA_PROD_API_KEY')
        if not api_key:
            logger.error("Environment variable ALMA_PROD_API_KEY is not set")
            raise ValueError("Environment variable ALMA_PROD_API_KEY is not set")
        else:
            # Mask API key for security in logs
            masked_key = api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]
            logger.debug(f"Using API key: {masked_key}")
        
        # Get configuration file path
        if args.config:
            config_path = args.config
            logger.info(f"Using configuration file from command line: {config_path}")
        else:
            config_path = resolve_config_path(args.config)
            logger.info(f"Using configuration file: {config_path}")
        
        # Load configuration
        logger.info("Loading configuration")
        config_manager = ConfigManager(config_path)
        region = config_manager.get_region()
        
        # Get all tasks from configuration
        logger.info("Getting tasks from configuration")
        all_tasks = config_manager.get_tasks()
        
        # Determine which tasks to run
        tasks_to_run = {}
        if args.tasks:
            logger.info(f"Specific tasks requested: {', '.join(args.tasks)}")
            # Check if specified tasks exist
            for task_name in args.tasks:
                if task_name in all_tasks:
                    tasks_to_run[task_name] = all_tasks[task_name]
                    logger.info(f"Task '{task_name}' found in configuration")
                else:
                    logger.warning(f"Task '{task_name}' not found in configuration. Skipping.")
            
            if not tasks_to_run:
                logger.error("None of the specified tasks were found in the configuration")
                raise ValueError("None of the specified tasks were found in the configuration")
        else:
            # Run all tasks if none specified
            tasks_to_run = all_tasks
            logger.info(f"No specific tasks requested, running all {len(all_tasks)} tasks")
        
        # Process selected tasks
        for task_name, task_config in tasks_to_run.items():
            logger.info(f"Starting task: {task_name}")
            
            collection_id = task_config['collection_id']
            report_paths = task_config['report_paths']
            
            # Create collection manager for this task
            logger.info(f"Creating collection manager for task '{task_name}' with collection ID: {collection_id}")
            manager = AlmaCollectionManager(
                api_key=api_key,
                collection_id=collection_id,
                region=region
            )
            
            # Update collection from the reports
            logger.info(f"Updating collection from reports for task '{task_name}'")
            manager.update_collection_from_reports(report_paths)
            
            logger.info(f"Task '{task_name}' completed successfully")
        
        logger.info("All specified tasks completed successfully")
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        exit(1)
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        exit(1)


def test_functionality():
    """
    Test function to verify the core functionality of the Alma Collection Manager.
    This uses print statements to show what's happening without making real API calls.
    """
    # Initialize logger
    logger_instance = Logger(log_level="DEBUG", log_dir="test_logs")
    logger = logging.getLogger(__name__)
    
    logger.info("=== Alma Collection Manager Test Mode ===")
    
    # Test 1: Configuration loading
    logger.info("[TEST 1] Loading Configuration")
    try:
        config_path = resolve_config_path()
        logger.debug(f"Looking for configuration file: {config_path}")
        
        config_manager = ConfigManager(config_path)
        logger.info("Configuration file loaded successfully")
        
        tasks = config_manager.get_tasks()
        logger.info(f"Found {len(tasks)} task(s) in configuration")
        
        for task_name, task_config in tasks.items():
            logger.debug(f"Task: {task_name}")
            logger.debug(f"Collection ID: {task_config['collection_id']}")
            logger.debug(f"Report Paths: {task_config['report_paths']}")
    except Exception as e:
        logger.error(f"Configuration loading failed: {e}")
        return
    
    # Test 2: API Key check
    logger.info("[TEST 2] Checking API Key")
    api_key = os.environ.get('ALMA_PROD_API_KEY')
    if not api_key:
        logger.warning("Environment variable ALMA_PROD_API_KEY is not set")
        logger.info("Using placeholder API key for testing: 'TEST_API_KEY'")
        api_key = 'TEST_API_KEY'
    else:
        logger.info("API Key found in environment variables")
        # Simple format check (not actual validation)
        if len(api_key) < 10:
            logger.warning("API key seems unusually short")
        # Mask the actual API key in output
        display_key = api_key[:4] + '*' * (len(api_key) - 8) + api_key[-4:]
        logger.debug(f"API Key: {display_key}")
    
    # Test 3: Simulate class initialization for first task
    logger.info("[TEST 3] Simulating Class Initialization")
    try:
        first_task_name = next(iter(tasks))
        first_task = tasks[first_task_name]
        
        collection_id = first_task['collection_id']
        region = config_manager.get_region()
        logger.debug(f"Creating AlmaCollectionManager for task: {first_task_name}")
        logger.debug(f"Collection ID: {collection_id}")
        logger.debug(f"Region: {region}")
        
        # Create a base URL for display purposes
        alma_base = f'https://api-{region}.hosted.exlibrisgroup.com/almaws/v1'
        logger.debug(f"Base URL: {alma_base}")
        
        if api_key:
            logger.info("All required parameters available for manager initialization")
        else:
            logger.warning("Missing API key for manager initialization")
    except Exception as e:
        logger.error(f"Class initialization simulation failed: {e}")
    
    # Test 4: Request simulation
    logger.info("[TEST 4] Simulating API Requests")
    try:
        # Simulate get_collection_count request
        count_url = f'{alma_base}/bibs/collections/{collection_id}/bibs'
        count_params = {'apikey': api_key, 'limit': 1}
        logger.debug("GET Collection Count Request:")
        logger.debug(f"URL: {count_url}")
        logger.debug(f"Params: {count_params}")
        logger.debug("Headers: {'Accept': 'application/json'}")
        
        # Simulate get_collection_mms_ids request (assuming count > 0)
        items_url = f'{alma_base}/bibs/collections/{collection_id}/bibs'
        items_params = {'apikey': api_key, 'limit': 100, 'offset': 0}
        logger.debug("GET Collection Items Request:")
        logger.debug(f"URL: {items_url}")
        logger.debug(f"Params: {items_params}")
        logger.debug("Headers: {'Accept': 'application/json'}")
        
        # Simulate delete request for an MMS ID
        delete_url = f'{alma_base}/bibs/collections/{collection_id}/bibs/sample_mms_id'
        delete_params = {'apikey': api_key}
        logger.debug("DELETE Remove Item Request:")
        logger.debug(f"URL: {delete_url}")
        logger.debug(f"Params: {delete_params}")
        
        # Simulate analytics report request
        report_paths = first_task['report_paths']
        for path in report_paths:
            report_url = f'{alma_base}/analytics/reports'
            report_params = {
                'path': path,
                'limit': 1000,
                'col_names': 'false',
                'apikey': api_key
            }
            logger.debug("GET Analytics Report Request:")
            logger.debug(f"URL: {report_url}")
            logger.debug(f"Params: {report_params}")
            logger.debug("Headers: {'Accept': 'application/xml'}")
        
        # Simulate add to collection request
        add_url = f'{alma_base}/bibs/collections/{collection_id}/bibs'
        add_params = {'apikey': api_key}
        add_body = {
            "link": "",
            "mms_id": "sample_mms_id",
            "record_format": "marc21",
            "suppress_from_publishing": "false",
            "suppress_from_external_search": "false",
            "suppress_from_metadoor": "false",
            "sync_with_oclc": "BIBS",
            "sync_with_libraries_australia": "NONE",
            "cataloging_level": {
                "value": "00"
            },
            "brief_level": {
                "value": "01"
            }
        }
        logger.debug("POST Add Item to Collection Request:")
        logger.debug(f"URL: {add_url}")
        logger.debug(f"Params: {add_params}")
        logger.debug("Headers: {'Accept': 'application/json'}")
        logger.debug(f"Body: {json.dumps(add_body, indent=2)}")
        
        logger.info("Request simulation completed")
    except Exception as e:
        logger.error(f"Request simulation failed: {e}")
    
    # Test 5: Simulating workflow
    logger.info("[TEST 5] Simulating Full Synchronization Workflow")
    try:
        report_paths = first_task['report_paths']
        logger.debug(f"Simulating synchronization workflow for collection: {collection_id}")

        # Simulate fetching MMS IDs from reports
        logger.debug(f"Step 1: Simulate fetching MMS IDs from {len(report_paths)} report(s).")
        simulated_report_mms_ids_list = ["MMSID1", "MMSID2", "MMSID3"] # Example: IDs from reports
        logger.debug(f"  → Simulated unique MMS IDs from reports: {simulated_report_mms_ids_list} (Count: {len(simulated_report_mms_ids_list)})")
        
        # Simulate scenario: No MMS IDs found in reports
        logger.info("[TEST 5a] Simulating Workflow - No MMS IDs Found in Reports")
        simulated_empty_report_mms_ids = []
        logger.debug(f"  Step 2a: Check if report MMS IDs are empty (simulated count: {len(simulated_empty_report_mms_ids)})")
        if not simulated_empty_report_mms_ids:
            logger.info("    → Simulated: No MMS IDs found in reports. Collection would not be modified.")
        logger.info("  Workflow simulation (No MMS IDs in Reports) completed.")

        # Continue with scenario where MMS IDs ARE found in reports
        logger.info("[TEST 5b] Simulating Workflow - MMS IDs Found in Reports (Synchronization Logic)")
        logger.debug(f"  Step 2b: Proceeding with report MMS IDs: {simulated_report_mms_ids_list}")

        # Simulate fetching current collection MMS IDs
        logger.debug("  Step 3: Simulate fetching current collection state.")
        simulated_current_collection_count = 2 
        simulated_current_collection_mms_ids_list = ["MMSID2", "MMSID4"] # Example: IDs currently in collection
        logger.debug(f"    → Simulated current collection count: {simulated_current_collection_count}")
        logger.debug(f"    → Simulated current collection MMS IDs: {simulated_current_collection_mms_ids_list} (Count: {len(simulated_current_collection_mms_ids_list)})")

        # Simulate calculating differences
        logger.debug("  Step 4: Simulate calculating differences.")
        report_set = set(simulated_report_mms_ids_list)
        current_set = set(simulated_current_collection_mms_ids_list)
        simulated_mms_ids_to_add = list(report_set - current_set)
        simulated_mms_ids_to_remove = list(current_set - report_set)
        logger.debug(f"    → Simulated MMS IDs to add: {simulated_mms_ids_to_add} (Count: {len(simulated_mms_ids_to_add)})")
        logger.debug(f"    → Simulated MMS IDs to remove: {simulated_mms_ids_to_remove} (Count: {len(simulated_mms_ids_to_remove)})")

        # Simulate adding items
        if simulated_mms_ids_to_add:
            logger.debug(f"  Step 5a: Simulate adding {len(simulated_mms_ids_to_add)} items to collection.")
            logger.debug(f"    → Would call add_to_collection with: {simulated_mms_ids_to_add}")
        else:
            logger.debug("  Step 5a: No items to add (simulated).")

        # Simulate removing items
        if simulated_mms_ids_to_remove:
            logger.debug(f"  Step 5b: Simulate removing {len(simulated_mms_ids_to_remove)} items from collection.")
            logger.debug(f"    → Would call remove_from_collection with: {simulated_mms_ids_to_remove}")
        else:
            logger.debug("  Step 5b: No items to remove (simulated).")
            
        logger.info("  Full synchronization workflow simulation completed.")

    except Exception as e:
        logger.error(f"Workflow simulation failed: {e}")
    
    logger.info("=== Test Completed ===")
    logger.info("The above requests would be made during actual execution.")
    logger.info("To run the actual tasks, use main() instead of test_functionality().")


if __name__ == "__main__":
    # Use main() for actual execution or test_functionality() for testing
    main()
    # test_functionality()