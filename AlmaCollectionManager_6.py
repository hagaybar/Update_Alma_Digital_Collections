#!/usr/bin/env python3
"""
Deprecated entry point, kept so existing scheduled tasks keep working.

The sync now lives in collection_sync.py. Point scheduled tasks at
collection_sync.py, then delete this file.
"""

from collection_sync import *  # noqa: F401,F403
from collection_sync import main

if __name__ == "__main__":
    main()
