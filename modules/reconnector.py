# modules/reconnector.py
# Handles the auto-reconnection logic with exponential backoff.

import asyncio
import logging
import os
from telethon import errors
from helpers.utils import ensure_awaitable
from config import BACKOFF_START, BACKOFF_MAX, SESSION_FILENAME
from client import client

logger = logging.getLogger(__name__)

# ---------- Reconnection Logic ----------


async def run_with_reconnect():
    backoff_time = BACKOFF_START
    while True:
        try:
            is_connected = await ensure_awaitable(client.is_connected())
            if not is_connected:
                logger.info("Connecting...")
                await ensure_awaitable(client.start())
                logger.info("Connected.")

            is_authorized = await ensure_awaitable(client.is_user_authorized())
            if not is_authorized:
                logger.warning("Not authorized. Re-starting...")
                await ensure_awaitable(client.start())
                logger.info("Re-authorized.")

            logger.info("Client running. Listening...")
            # Use run_until_disconnected which handles Telegram-level reconnections
            # This loop only handles startup and auth issues.
            await client.run_until_disconnected()

        except (OSError, ConnectionError, TimeoutError, asyncio.CancelledError) as e:
            logger.warning(f"Net err: {repr(e)}. Reconnecting...")
            # Reset backoff after a successful connection attempt fails
            backoff_time = BACKOFF_START
            # No sleep here for immediate retry attempt after network issues

        except errors.AuthKeyUnregisteredError as e:
            logger.error(f"Auth err: {repr(e)}")
            logger.info(f"Deleting session '{SESSION_FILENAME}'...")
            try:
                if os.path.exists(SESSION_FILENAME):
                    os.remove(SESSION_FILENAME)
                    logger.info("Session deleted. Re-login required.")
            except Exception as del_err:
                logger.error(f"Del session err: {repr(del_err)}")
            # Reset backoff for auth issues, then sleep briefly before restart
            backoff_time = BACKOFF_START
            try:
                await ensure_awaitable(client.start())
                logger.info("Re-started after auth err.")
            except Exception as start_err:
                logger.error(f"Restart err: {repr(start_err)}")
                # Sleep briefly if restart fails, then continue loop
                await asyncio.sleep(backoff_time)
                backoff_time = min(backoff_time * 2, BACKOFF_MAX)

        except errors.FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"Flood wait: {wait_time}s. Sleeping...")
            # Sleep for the required time or current backoff, whichever is larger
            await asyncio.sleep(max(wait_time, backoff_time))

        except errors.RPCError as e:
            logger.error(f"RPC err: {repr(e)}. Reconnecting...")
            # Reset backoff for general RPC errors and retry immediately
            backoff_time = BACKOFF_START
            # No sleep here for immediate retry

        except Exception as e:
            logger.error(f"Unexpected err: {repr(e)}. Reconnecting...")
            # Reset backoff for unexpected errors and retry immediately
            backoff_time = BACKOFF_START
            # No sleep here for immediate retry


def setup(client_instance):
    """Setup function called by the module loader."""
    # The reconnection logic is typically started from main.py
    # This function can be used for any additional setup if needed in the future.
    logger.info("Reconnector module loaded (logic will be started from main).")
    pass


# Define HELP_TEXT for the help command (reconnector itself doesn't add a command)
# We can provide a general info line if desired, or leave it empty.
HELP_TEXT = ""  # Or something like "• General: Auto-reconnect enabled.\n"
# Since it doesn't add a user-facing command, an empty string is often appropriate.
