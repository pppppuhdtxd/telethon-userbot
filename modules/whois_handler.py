# modules/whois_handler.py
# Handles the 'whois' command to display information about a replied user,
# a specified username/chat, or the current chat if no reply is made.

import logging
import re
from telethon import events
from telethon.utils import get_display_name
from telethon.tl.types import User, Chat, Channel
from client import client

logger = logging.getLogger(__name__)


@client.on(events.NewMessage(outgoing=True))
async def handle_whois_command(event):
    """Displays user/channel/group information based on command arguments or context."""
    text = (event.raw_text or "").strip()

    # Check for the 'whois' command
    if text.lower().startswith("whois"):
        parts = text.split()
        # Determine the target for whois
        target = None

        # Case 1: whois @username (or numeric ID)
        if len(parts) > 1:
            identifier = parts[1]
            try:
                # Attempt to resolve the identifier (username or numeric ID)
                target = await client.get_entity(identifier)
                logger.debug(
                    f"Whois: Resolved identifier '{identifier}' to entity {target.id}")
            except Exception as e:
                error_msg = f"❌ Could not resolve '{identifier}' to an entity: {repr(e)}"
                logger.error(f"Whois command error: {error_msg}")
                await event.edit(error_msg)
                return
        # Case 2: whois (with reply)
        elif event.is_reply:
            reply_msg = await event.get_reply_message()
            if not reply_msg:
                whois_text = "Could not get the replied message."
                await event.edit(whois_text)
                logger.debug("Whois command: replied message not found.")
                return

            try:
                # Get the sender of the replied message
                target = await reply_msg.get_sender()
                if not target:
                    whois_text = "Could not get sender info."
                    await event.edit(whois_text)
                    logger.debug("Whois command: could not get sender.")
                    return
            except Exception as e:
                whois_text = f"Error getting sender info: {repr(e)}"
                await event.edit(whois_text)
                logger.error(f"Whois command error (reply): {repr(e)}")
                return
        # Case 3: whois (no reply, no identifier) -> Get current chat info
        else:
            try:
                target = await event.get_chat()
                if not target:
                    whois_text = "Could not get current chat info."
                    await event.edit(whois_text)
                    logger.debug("Whois command: could not get current chat.")
                    return
            except Exception as e:
                whois_text = f"Error getting current chat info: {repr(e)}"
                await event.edit(whois_text)
                logger.error(f"Whois command error (current chat): {repr(e)}")
                return

        # Format and send the information based on the target entity type
        if target:
            whois_lines = []
            entity_id = getattr(target, 'id', 'N/A')
            whois_lines.append(f"ID: {entity_id}")

            # Handle User, Chat, Channel differently
            if isinstance(target, User):
                # User-specific attributes
                username = getattr(target, 'username', 'N/A')
                first_name = getattr(target, 'first_name', 'N/A')
                last_name = getattr(target, 'last_name', '')
                full_name = f"{first_name} {last_name}".strip(
                ) if last_name else first_name
                is_bot = getattr(target, 'bot', False)

                whois_lines.append(f"Type: User")
                whois_lines.append(
                    f"Username: @{username}" if username != 'N/A' else "Username: N/A")
                whois_lines.append(f"Display Name: {full_name}")
                whois_lines.append(f"Bot: {is_bot}")

            elif isinstance(target, (Chat, Channel)):
                # Chat/Channel-specific attributes
                title = get_display_name(target)
                username = getattr(target, 'username', 'N/A')
                # May not always be available depending on access
                participants_count = getattr(
                    target, 'participants_count', 'N/A')
                is_channel = isinstance(target, Channel)
                # Channels have megagroup attr, Chats don't
                is_supergroup = is_channel and getattr(
                    target, 'megagroup', False)
                is_group = isinstance(target, Chat) or (
                    is_channel and not is_supergroup)

                whois_lines.append(
                    f"Type: {'Channel' if is_channel else 'Group (Legacy)'}")
                if is_supergroup:
                    whois_lines.append("Type: Supergroup (Channel-style)")
                whois_lines.append(f"Title: {title}")
                whois_lines.append(
                    f"Username: @{username}" if username != 'N/A' else "Username: N/A")
                # Note: might be N/A for channels without permission
                whois_lines.append(
                    f"Participants/Members: {participants_count}")

            else:
                # Fallback for unexpected types
                whois_lines.append(f"Type: {type(target).__name__}")

            full_whois = "\n".join(whois_lines)
            await event.edit(f"--- Whois Info ---\n{full_whois}\n------------------")
            logger.debug("Whois command executed and message edited.")
        else:
            await event.edit("Could not determine target for whois.")
            logger.debug("Whois command: target was None after all checks.")


def setup(client_instance):
    """Setup function called by the module loader."""
    # The event handler is already registered using the decorator @client.on
    # This function can be used for any additional setup if needed in the future.
    logger.info(
        "Whois handler module loaded (supports @username, replied msg, and current chat).")
    pass


# Define HELP_TEXT for the help command
HELP_TEXT = "**دستورهای دیگر:**\n• `whois`  نمایش اطلاعات چت فعلی\n• `whois @username`  نمایش اطلاعات یوزرنیم مورد نظر\n• `whois` (در پاسخ به پیام) - نمایش اطلاعات فرد/کانال/گروه ارسال کننده پیام ریپلای شده\n\n"
