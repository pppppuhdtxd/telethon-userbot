# modules/help_handler.py
# Handles the 'help' command to display a list of commands and their descriptions.

import logging
from telethon import events
from client import client
from core.module_loader import get_aggregated_help_texts # Import the collected help texts

logger = logging.getLogger(__name__)

@client.on(events.NewMessage(outgoing=True))
async def handle_help_command(event):
    """Displays a help message with available commands when 'help' is sent in Saved Messages."""
    text = (event.raw_text or "").strip()

    if text == "help":
        # Get the 'me' user (yourself) to identify Saved Messages
        me = await client.get_me()
        # The chat_id for Saved Messages is usually your own user ID
        if event.chat_id == me.id:
            # Retrieve dynamic help text from modules
            dynamic_help_text = "".join(get_aggregated_help_texts()) # Join the list into a single string

            # Add static help text that doesn't come from modules
            static_help_text = "**دستورهای دیگر:**\n• `help` - نمایش این راهنما\n\n"

            full_help_text = f"📋 **راهنمای دستورات**:\n\n{dynamic_help_text}{static_help_text}"
            await event.edit(full_help_text)
            logger.debug("Help command executed and message edited in Saved Messages.")
        else:
            logger.debug("Help command ignored - not in Saved Messages.")
        return # Exit after handling 'help' or ignoring it

def setup(client_instance):
    """Setup function called by the module loader."""
    # The event handler is already registered using the decorator @client.on
    # This function can be used for any additional setup if needed in the future.
    logger.info("Help handler module loaded.")
    pass

# Define HELP_TEXT for the help command (this module doesn't add new commands, just the base command itself)
# We add the 'help' command info in the static text within the handler itself.
# If we wanted to add it dynamically here, we could, but it's simpler to manage in the handler.
# For now, this module's HELP_TEXT can be empty or just a placeholder if required by loader structure.
# As the help handler *is* the provider of the final text, it might not need its own HELP_TEXT appended.
# The loader aggregates *other* modules' HELP_TEXT.
# However, if the loader expects *every* module to have it, we can define an empty one:
HELP_TEXT = "" # Or define it if the base 'help' command description should come from here too.
# Actually, since the help text for 'help' is static and managed *within* the handler itself,
# it's better to keep it out of the dynamic list. So an empty string is appropriate here.