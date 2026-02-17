# core/client_manager.py
# Initializes and provides the TelegramClient instance.

import logging
from telethon import TelegramClient
from config import API_ID, API_HASH, SESSION_NAME

logger = logging.getLogger(__name__)

# ---------- Setup client ----------
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

def get_client():
    """Returns the global client instance."""
    return client

async def start_client():
    """Starts the client and ensures it's authorized."""
    logger.info("Initializing Telegram client...")
    await client.start()
    logger.info("Client initialized and connected.")
    if not await client.is_user_authorized():
        logger.warning("Client is not authorized. Please run the script and log in.")
        # client.start() will prompt for login if not authorized
        await client.start()
        logger.info("Client re-authorized.")