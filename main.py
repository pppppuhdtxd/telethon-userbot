# main.py
# Main entry point for the userbot application.
# Initializes the client, loads modules, and starts the reconnection loop.

import asyncio
import logging
from client import client
from core.module_loader import load_modules
from modules.reconnector import run_with_reconnect


# ---------- Custom Log Filter ----------
class IgnoreChannelDiffFilter(logging.Filter):
    """Filter to suppress Telethon's 'Got difference for channel ...' log messages."""

    def filter(self, record):
        # Suppress only logs containing this specific phrase
        return "Got difference for channel" not in record.getMessage()


# ---------- Logging Setup ----------
logging.basicConfig(
    format='%(message)s',
    level=logging.INFO  # Keep INFO level for other useful logs
)

# Apply the custom filter to the root logger
logging.getLogger().addFilter(IgnoreChannelDiffFilter())

# NEW: Set the Telethon logger's level to WARNING to suppress INFO logs like "Got difference for channel"
logging.getLogger('telethon').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------- Run ----------
def main():
    """Start the userbot client with auto-reconnect and loaded modules."""
    logger.info(
        "Starting userbot client with auto-reconnect and dynamic modules...")
    load_modules()
    logger.info("All modules loaded.")
    asyncio.run(run_with_reconnect())


if __name__ == "__main__":
    main()
