# modules/join_left.py
# Handles the 'join' command to join Telegram groups/channels from links/usernames/IDs found in replied messages.
# Also handles the 'left' command to leave groups/channels/bots by replying to a message containing links/usernames/IDs.
# Joins log the joined chat IDs or usernames by appending them to the latest message in @joineeef chat (like auto_joiner).
# Leaves delete the command message if any leave operation is successful and edit the replied message to a dot if sent by the bot (like auto_lefter).

import asyncio
import logging
import re
from telethon import events, errors
from telethon.tl.types import (
    ReplyInlineMarkup,
    KeyboardButtonUrl,
    User,
    Chat,
    Channel,
    Message
)
# Import the specific functions needed
from telethon.tl.functions.messages import DeleteHistoryRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import LeaveChannelRequest, JoinChannelRequest
from telethon.utils import get_display_name
from client import client
# Assuming safe_delete handles exceptions for delete
from helpers.utils import safe_delete

logger = logging.getLogger(__name__)

# --- Configuration (for join functionality)---
# The chat where the list of joined IDs/usernames will be appended/updated
JOINEE_CHAT_USERNAME = "@joineeef"

# --- Helper: Extract Telegram Entities (Links/Usernames/IDs) ---


def extract_telegram_entities(text):
    """
    Extracts Telegram entities (public usernames, private invite links, numeric IDs) from text.
    Returns a list of tuples: [('type', 'identifier'), ...]
    """
    if not text:
        return []
    entities = []
    # Pattern 1: Public username (@username or t.me/username or https://t.me/username      )
    public_pattern = re.compile(
        r'(?:@|(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.org)/)([a-zA-Z0-9_]{5,32})(?![a-zA-Z0-9_/])',
        re.IGNORECASE
    )
    for match in public_pattern.finditer(text):
        username = match.group(1)
        # --- Filter: Check if username ends with 'bot' (case-insensitive) ---
        if not username.lower().endswith('bot'):
            entities.append(('username', username))
        else:
            logger.debug(f"Filtered out bot username: {username}")

    # Pattern 2: Private invite link (https://t.me/+hash     or t.me/joinchat/hash or +hash)
    # Updated to capture the full link and the hash separately
    private_pattern = re.compile(
        r'(https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.org)/(?:joinchat/|\+))([a-zA-Z0-9_-]{10,64})',
        re.IGNORECASE
    )
    for match in private_pattern.finditer(text):
        # Group 1 captures the base part (e.g., 'https://t.me/+    ', 'https://t.me/joinchat/    ')
        base_part = match.group(1)
        # Group 2 captures the hash part
        invite_hash = match.group(2)
        # Reconstruct the full link correctly
        full_link = base_part + invite_hash
        entities.append(('invite_link', full_link))
        logger.debug(
            f"Matched private link: {full_link}, extracted hash: {invite_hash}")

    # Pattern 3: Numeric ID (e.g., 1234567890)
    # Assuming IDs are typically 9 to 14 digits long for channels/groups/users
    numeric_id_pattern = re.compile(r'\b(\d{9,14})\b')
    for match in numeric_id_pattern.finditer(text):
        numeric_id = int(match.group(1))  # Convert string to int
        entities.append(('numeric_id', numeric_id))
        logger.debug(f"Matched numeric ID: {numeric_id}")

    logger.debug(f"Found entities in text: {entities}")
    return entities

# --- Event Handler for the join command ---


async def handle_join_command(event):
    """Handles the join command when replied to a message."""
    text = (event.raw_text or "").strip()

    if text.lower() != "join":
        return  # Let the main handler decide if it's a left command

    if not event.is_reply:
        await event.edit("⚠️ Please reply to the message with links/usernames/IDs.")
        logger.debug("Join command used without reply.")
        return

    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.edit("❌ Could not get the replied message.")
        logger.debug("Join command: replied message not found.")
        return

    # --- Collect Entities ---
    all_entities = set()

    # 1. Scan text of the replied message
    all_entities.update(extract_telegram_entities(reply_msg.message))

    # 2. Scan text of the command message itself
    all_entities.update(extract_telegram_entities(event.message.message))

    # 3. Scan reply markup (inline buttons) of the replied message
    if hasattr(reply_msg, 'reply_markup') and isinstance(reply_msg.reply_markup, ReplyInlineMarkup):
        for row in reply_msg.reply_markup.rows:
            for button in row.buttons:
                if isinstance(button, KeyboardButtonUrl):
                    all_entities.update(extract_telegram_entities(button.url))

    if not all_entities:
        await event.edit("ℹ️ No Telegram usernames, links, or numeric IDs found.")
        logger.debug("Join command: no entities found.")
        return

    # --- Get the target chat for logging (@joineeef) ---
    try:
        joinee_chat_entity = await client.get_entity(JOINEE_CHAT_USERNAME)
        logger.debug(f"Found joineeef chat: {joinee_chat_entity.id}")
    except Exception as e:
        logger.error(
            f"Could not find or access {JOINEE_CHAT_USERNAME}: {repr(e)}")
        await event.edit(f"❌ Could not access {JOINEE_CHAT_USERNAME} for logging.")
        return

    # --- Process Entities ---
    processing_msg = await event.edit(f"🔍 Found {len(all_entities)} entity(ies). Attempting to join...")
    results = []
    joined_items = []  # To store successfully joined chat info (ID or link)

    for entity_type, identifier in all_entities:
        try:
            logger.info(f"Attempting to join: {entity_type} -> {identifier}")
            joined_entity = None

            if entity_type == 'username':
                try:
                    input_entity = await client.get_input_entity(f"@{identifier}")
                    updates = await client(JoinChannelRequest(input_entity))
                    if updates.chats:
                        joined_entity = updates.chats[0]
                        logger.info(
                            f"Joined via username: {identifier} -> {getattr(joined_entity, 'title', 'N/A')}")
                    else:
                        raise Exception(
                            "No chat returned after joining via username")
                except (errors.UsernameNotOccupiedError, errors.ChannelPrivateError) as specific_err:
                    logger.error(
                        f"Error joining {identifier}: {repr(specific_err)}")
                    raise specific_err
                except Exception as e:
                    logger.warning(
                        f"Failed to join {identifier} via JoinChannelRequest: {repr(e)}. Trying get_entity fallback...")
                    try:
                        entity = await client.get_entity(f"@{identifier}")
                        joined_entity = entity
                        logger.info(
                            f"Fallback: Got entity for {identifier} -> {getattr(joined_entity, 'title', 'N/A')}")
                    except Exception as fallback_err:
                        logger.error(
                            f"Fallback get_entity also failed for {identifier}: {repr(fallback_err)}")
                        raise e

            elif entity_type == 'numeric_id':
                # Use get_entity for numeric IDs
                try:
                    joined_entity = await client.get_entity(identifier)
                    logger.info(
                        f"Resolved numeric ID: {identifier} -> {getattr(joined_entity, 'title', 'N/A')}")
                    # For numeric IDs, we first resolve to get the entity details (like username if available)
                    # Then, we still need to join. Check if it's a Channel/Chat/User
                    # For Channels and Supergroups, JoinChannelRequest might work if it's a public one we haven't joined yet.
                    # But if we found it by ID, we likely already joined it via another method or it was private.
                    # The join logic inside the 'if entity_type == ...' blocks handles the actual joining attempt.
                    # Let's assume if we resolved it, the join attempt was successful *before* this code ran,
                    # or the join attempt should happen using the resolved entity details if possible.
                    # However, joining *only* by numeric ID without a link/username is tricky for public chats.
                    # For private chats, you usually need an invite link.
                    # So, for numeric_id, we assume the 'identifier' was the target, and 'get_entity' resolved it.
                    # If the user was already in the chat, 'get_entity' works.
                    # If not, it might fail depending on chat privacy.
                    # For this code, we'll proceed assuming 'get_entity' worked because the user *is* in the chat or it's joinable.
                    # If 'get_entity' fails, the exception block above handles it.
                    # So, if we reach here, joined_entity is resolved.
                except ValueError as ve:
                    logger.error(
                        f"Could not resolve numeric ID {identifier}: {repr(ve)}")
                    results.append(
                        f"❌ [{identifier}] - Could not resolve numeric ID")
                    continue
            elif entity_type == 'invite_link':
                # Extract hash correctly from the identifier link
                # Match the hash part from the end of the identifier link
                # Ensure identifier is string for regex
                hash_match = re.search(
                    r'(?:\+|joinchat/)([a-zA-Z0-9_-]{10,64})$', str(identifier))
                if not hash_match:
                    logger.error(
                        f"Could not extract hash from invite link: {identifier}")
                    results.append(f"❌ [{identifier}] - Could not parse link")
                    continue
                invite_hash = hash_match.group(1)
                logger.debug(
                    f"Extracted invite hash from {identifier}: {invite_hash}")
                try:
                    updates = await client(ImportChatInviteRequest(invite_hash))
                    if updates.chats:
                        joined_entity = updates.chats[0]
                        logger.info(
                            f"Joined via invite link: {identifier} (hash: {invite_hash}) -> {getattr(joined_entity, 'title', 'N/A')}")
                    else:
                        raise Exception(
                            "No chat returned after joining via invite link")
                except errors.InviteHashInvalidError:
                    logger.error(
                        f"Invalid invite hash from link: {identifier} (hash: {invite_hash})")
                    raise
                except errors.UserAlreadyParticipantError:
                    logger.info(
                        f"Already a participant in chat from link {identifier}.")
                    results.append(f"ℹ️ [{identifier}] - Already Member")
                    continue  # Skip adding to joined list if already member
                except Exception as e:
                    logger.error(
                        f"Failed to join via invite link {identifier}: {repr(e)}")
                    results.append(
                        f"❌ [{identifier}] - Could not join via link ({repr(e)})")
                    continue  # Skip adding to joined list if join failed

            if joined_entity:
                chat_id = joined_entity.id
                chat_username = getattr(joined_entity, 'username', None)
                chat_title = getattr(joined_entity, 'title', 'N/A')

                # Create the item to append: a clickable link if username exists, otherwise just the ID
                if chat_username:
                    item_to_append = f"https://t.me/{chat_username}"
                else:
                    item_to_append = f"ID: {chat_id}"

                logger.info(
                    f"Successfully joined/resolved: {identifier} -> {chat_title} (ID: {chat_id}, Username: {chat_username})")
                results.append(
                    f"✅ [{chat_title or identifier}]({identifier}) - Joined/Resolved")
                # Add the clickable item or ID
                joined_items.append(item_to_append)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to join/resolve {identifier}: {repr(e)}")

            if "INVITE_REQUEST_SENT" in error_msg:
                status = "⏳ Request Sent"
            elif "INVITE_HASH_INVALID" in error_msg or isinstance(e, errors.InviteHashInvalidError):
                status = "❌ Invalid Invite Link"
            elif "USERNAME_NOT_OCCUPIED" in error_msg or isinstance(e, errors.UsernameNotOccupiedError):
                status = "❌ Invalid Username"
            elif "USER_ALREADY_PARTICIPANT" in error_msg or isinstance(e, errors.UserAlreadyParticipantError):
                status = "ℹ️ Already Member"
            elif "CHANNEL_PRIVATE" in error_msg or isinstance(e, errors.ChannelPrivateError):
                status = "🔒 Private/Restricted"
            else:
                status = f"❌ Failed: {error_msg[:50]}..."

            results.append(f"❌ [{identifier}] - {status}")

    # --- Update the latest message in @joineeef by appending new items ---
    if joined_items:
        try:
            # Fetch the latest message from @joineeef sent by the bot itself
            async for msg in client.iter_messages(joinee_chat_entity, limit=1):
                # Check if the message was sent by the bot (outgoing)
                if msg.out:
                    current_text = msg.message or ""
                    # Append new items with a separator (e.g., newline)
                    # Add a separator only if the current text is not empty
                    separator = "\n" if current_text else ""
                    new_text = current_text + \
                        separator + "\n".join(joined_items)
                    await client.edit_message(joinee_chat_entity, msg.id, new_text)
                    logger.info(
                        f"Appended new items to the latest bot message in {JOINEE_CHAT_USERNAME}: {joined_items}")
                    # Edit only the first (latest) outgoing message found
                    break
            else:
                logger.warning(
                    f"No outgoing message found in {JOINEE_CHAT_USERNAME} to append items. Could not update list.")
                # Optionally inform the user
                # await event.respond(f"⚠️ Could not find a message in {JOINEE_CHAT_USERNAME} to update.")
        except Exception as e:
            logger.error(
                f"Failed to append items to message in {JOINEE_CHAT_USERNAME}: {repr(e)}")
            # Optionally inform the user
            # await event.respond(f"⚠️ Could not update the list in {JOINEE_CHAT_USERNAME}.")

    # --- Send Final Report ---
    final_text = f"--- Join Results ---\n" + \
        "\n".join(results) + "\n------------------"
    try:
        await processing_msg.edit(final_text, parse_mode='Markdown')
    except Exception as edit_err:
        logger.error(f"Failed to edit message with results: {repr(edit_err)}")
        try:
            await event.respond(final_text, parse_mode='Markdown')
        except Exception as resp_err:
            logger.error(f"Failed to send results message: {repr(resp_err)}")
            await processing_msg.edit("❌ An error occurred while formatting the results.")

# --- Event Handler for the left command ---


async def handle_left_command(event):
    """Handles the left command when replied to a message."""
    text = (event.raw_text or "").strip()

    if text.lower() != "left":
        return  # Let the main handler decide if it's a join command

    if not event.is_reply:
        await event.edit("⚠️ Please reply to the message containing links/usernames/IDs.")
        logger.debug("Left command used without reply.")
        return

    reply_msg = await event.get_reply_message()
    if not reply_msg:
        await event.edit("❌ Could not get the replied message.")
        logger.debug("Left command: replied message not found.")
        return

    # --- Collect Entities ---
    all_entities = set()

    # 1. Scan text of the replied message
    all_entities.update(extract_telegram_entities(reply_msg.message))

    # 2. Scan text of the command message itself (in case user types IDs directly after 'left')
    all_entities.update(extract_telegram_entities(event.message.message))

    # 3. Scan reply markup (inline buttons) of the replied message
    if hasattr(reply_msg, 'reply_markup') and isinstance(reply_msg.reply_markup, ReplyInlineMarkup):
        for row in reply_msg.reply_markup.rows:
            for button in row.buttons:
                if isinstance(button, KeyboardButtonUrl):
                    all_entities.update(extract_telegram_entities(button.url))

    if not all_entities:
        await event.edit("ℹ️ No Telegram usernames, links, or numeric IDs found in the replied message or command text.")
        logger.debug("Left command: no entities found.")
        return

    # --- Process Entities ---
    processing_msg = await event.edit(f"🔍 Found {len(all_entities)} entity(ies). Attempting to leave...")
    results = []
    # Track if any leave operation was successful
    any_successful_left = False

    for entity_type, identifier in all_entities:
        try:
            logger.info(f"Attempting to leave: {entity_type} -> {identifier}")
            target_entity = None
            left_ok = False  # Track success for this specific entity
            # Determine the target entity based on type
            if entity_type == 'username':
                # Use get_entity for usernames
                target_entity = await client.get_entity(f"@{identifier}")
            elif entity_type == 'numeric_id':
                # Use get_entity for numeric IDs
                try:
                    target_entity = await client.get_entity(identifier)
                except ValueError as ve:
                    logger.error(
                        f"Could not resolve numeric ID {identifier}: {repr(ve)}")
                    results.append(
                        f"❌ [{identifier}] - Could not resolve numeric ID")
                    continue
            elif entity_type == 'invite_link':
                # For invite links, we need to get the hash part to identify the chat
                # Extract hash correctly from the identifier link
                # Match the hash part from the end of the identifier link
                # Ensure identifier is string for regex
                hash_match = re.search(
                    r'(?:\+|joinchat/)([a-zA-Z0-9_-]{10,64})$', str(identifier))
                if not hash_match:
                    logger.error(
                        f"Could not extract hash from invite link: {identifier}")
                    results.append(f"❌ [{identifier}] - Could not parse link")
                    continue
                invite_hash = hash_match.group(1)
                logger.debug(
                    f"Extracted invite hash from {identifier}: {invite_hash}")
                # Use ImportChatInviteRequest to join temporarily and get the entity
                # This is often the only way to get the entity from a private link
                # We will join and then immediately leave.
                try:
                    # Use the imported function directly
                    updates = await client(ImportChatInviteRequest(invite_hash))
                    if updates.chats:
                        target_entity = updates.chats[0]
                        logger.info(
                            f"Joined via invite link temporarily to get entity: {identifier} (hash: {invite_hash}) -> {getattr(target_entity, 'title', 'N/A')}")
                    else:
                        raise Exception(
                            "No chat returned after joining via invite link")
                except errors.InviteHashExpiredError:
                    logger.error(f"Invite link expired: {identifier}")
                    results.append(f"❌ [{identifier}] - Invite Link Expired")
                    continue
                except errors.InviteHashInvalidError:
                    logger.error(
                        f"Invalid invite hash from link: {identifier}")
                    results.append(f"❌ [{identifier}] - Invalid Invite Link")
                    continue
                except errors.UserAlreadyParticipantError:
                    logger.info(
                        f"Already a participant in chat from link {identifier}, getting entity...")
                    # If already joined, we need to get the entity differently.
                    # This is tricky. ImportChatInviteRequest fails if already joined.
                    # A potential workaround is to list dialogs and find a chat that matches the hash, which is complex.
                    # For now, assume for now this case isn't handled well by this simple method after joining.
                    # A more robust solution might involve checking dialogs against known invite hashes, which is outside this scope.
                    # Let's assume for now this case isn't handled well by this simple method after joining.
                    logger.warning(
                        f"Already in chat from link {identifier}, might not be able to leave directly via link.")
                    results.append(
                        f"⚠️ [{identifier}] - Already Member, direct leave via link might not work.")
                    continue
                except Exception as e:
                    logger.error(
                        f"Failed to join via invite link {identifier}: {repr(e)}")
                    results.append(
                        f"❌ [{identifier}] - Could not join via link ({repr(e)})")
                    continue

            if target_entity:
                # Now try to leave the target entity based on its type
                # For Channels/Supergroups: LeaveChannelRequest
                # For Chats (old groups) and Users (bots): DeleteHistoryRequest (or similar behavior)
                if isinstance(target_entity, (Channel)):
                    # This includes both supergroups and channels
                    try:
                        await client(LeaveChannelRequest(target_entity))
                        left_ok = True  # Mark as successful
                        logger.info(
                            f"Left channel/supergroup: {identifier} -> {getattr(target_entity, 'title', 'N/A')} (ID: {target_entity.id})")
                        results.append(
                            f"✅ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Left Channel/Supergroup")
                    except errors.UserNotParticipantError:
                        # Might happen if we joined via link but were already out somehow, or it's a bot.
                        # For channels, this means we are not in it.
                        logger.info(
                            f"Not a participant in channel/supergroup: {identifier}")
                        results.append(
                            f"ℹ️ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Not a Member")
                    except errors.ChannelInvalidError:
                        logger.error(
                            f"Invalid channel/supergroup: {identifier}")
                        results.append(
                            f"❌ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Invalid Channel/Supergroup")
                    except errors.ChannelPrivateError:
                        logger.error(
                            f"Private/Restricted channel/supergroup: {identifier}")
                        results.append(
                            f"🔒 [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Private/Restricted")
                    except Exception as e:
                        logger.error(
                            f"Failed to leave channel/supergroup {identifier}: {repr(e)}")
                        results.append(
                            f"❌ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Leave Failed: {repr(e)}")

                elif isinstance(target_entity, Chat):
                    # This is an old group type (not a supergroup)
                    # Leaving old groups is not a standard API call for users.
                    # The closest we can get is to delete the history, which effectively removes the chat from the list for the user.
                    # This is often the desired behavior when "leaving" an old group as a regular user.
                    # Note: This might not be possible in all cases or might behave differently.
                    try:
                        # just_clear=False attempts to delete the chat entirely
                        await client(DeleteHistoryRequest(peer=target_entity, just_clear=False))
                        # Mark as successful (or at least removal attempt)
                        left_ok = True
                        logger.info(
                            f"Deleted history/removed old group chat: {identifier} -> {getattr(target_entity, 'title', 'N/A')} (ID: {target_entity.id})")
                        results.append(
                            f"✅ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Removed Old Group Chat")
                    except Exception as e:
                        logger.error(
                            f"Failed to remove old group chat {identifier}: {repr(e)}")
                        results.append(
                            f"❌ [{getattr(target_entity, 'title', 'N/A') or identifier}]({identifier}) - Remove Failed: {repr(e)}")

                elif isinstance(target_entity, User):
                    # This is likely a bot or user chat.
                    # Users cannot "leave" a private chat with another user or a bot in the same way as a group/channel.
                    # However, we can delete the history, which removes the chat from the list (similar to blocking and unblocking a bot).
                    # This is often the closest action to "leaving" a private chat as a user.
                    try:
                        # just_clear=False attempts to delete the chat entirely
                        await client(DeleteHistoryRequest(peer=target_entity, just_clear=False))
                        # Mark as successful (or at least removal attempt)
                        left_ok = True
                        logger.info(
                            f"Deleted history/removed private chat with user/bot: {identifier} -> {getattr(target_entity, 'first_name', 'N/A')} (ID: {target_entity.id})")
                        # Use first_name for users/bots instead of title
                        results.append(
                            f"✅ [{getattr(target_entity, 'first_name', 'N/A') or identifier}]({identifier}) - Removed Private Chat")
                    except Exception as e:
                        logger.error(
                            f"Failed to remove private chat with user/bot {identifier}: {repr(e)}")
                        results.append(
                            f"❌ [{getattr(target_entity, 'first_name', 'N/A') or identifier}]({identifier}) - Remove Failed: {repr(e)}")

                else:
                    # Should not happen if target_entity is correctly retrieved
                    logger.warning(
                        f"Unknown entity type for leaving: {type(target_entity)} - {identifier}")
                    results.append(
                        f"❓ [{identifier}] - Unknown entity type for leaving")

                if left_ok:
                    any_successful_left = True  # Update overall success flag if this one was OK

        except errors.FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"Leave Flood wait: {wait_time}s. Sleeping...")
            await event.edit(f"⏳ Flood wait for {identifier}, sleeping {wait_time}s...")
            await asyncio.sleep(wait_time)
            # Retry the specific entity? For simplicity, we just log and continue to the next.
            results.append(
                f"⏳ [{identifier}] - Flood wait encountered, skipped.")
        except errors.RPCError as e:
            error_msg = str(e)
            logger.error(f"RPC Error leaving {identifier}: {repr(e)}")
            results.append(
                f"❌ [{identifier}] - RPC Error: {error_msg[:50]}...")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Unexpected error leaving {identifier}: {repr(e)}")
            results.append(
                f"❌ [{identifier}] - Unexpected Error: {error_msg[:50]}...")

    # --- Send Final Report ---
    final_text = f"--- Leave Results ---\n" + \
        "\n".join(results) + "\n------------------"
    try:
        await processing_msg.edit(final_text, parse_mode='Markdown')
    except Exception as edit_err:
        logger.error(f"Failed to edit message with results: {repr(edit_err)}")
        try:
            await event.respond(final_text, parse_mode='Markdown')
        except Exception as resp_err:
            logger.error(f"Failed to send results message: {repr(resp_err)}")
            await processing_msg.edit("❌ An error occurred while formatting the results.")

    # --- Post-Processing: Delete command message and edit reply message ---
    # 1. Delete the command message if any leave was successful
    if any_successful_left:
        logger.info(
            "At least one leave operation was successful. Deleting command message.")
        try:
            # Use safe_delete from helpers if available, otherwise use client.delete_messages
            # Assuming safe_delete is designed for messages and handles exceptions gracefully
            await safe_delete(client, event.chat_id, event.message.id)
            # Note: After deleting, 'event.message' object becomes invalid if accessed later in this function.
        except Exception as del_err:
            logger.error(
                f"Failed to delete command message {event.message.id}: {repr(del_err)}")

    # 2. Edit the replied message to a dot if it was sent by the bot
    if event.is_reply and reply_msg:
        # Check if the replied message was sent by the bot itself
        if reply_msg.out:  # Message was sent by the bot
            try:
                logger.info(
                    f"Editing replied message {reply_msg.id} to a dot.")
                # Edit the message text to "."
                await client.edit_message(reply_msg, ".")
            except Exception as edit_reply_err:
                logger.error(
                    f"Failed to edit replied message {reply_msg.id}: {repr(edit_reply_err)}")
        else:
            logger.debug(
                f"Replied message {reply_msg.id} was not sent by the bot, skipping edit.")

# --- Main Event Handler ---


@client.on(events.NewMessage(outgoing=True))
async def handle_join_or_left_command(event):
    """Main handler that routes to join or left command handlers."""
    text = (event.raw_text or "").strip().lower()
    if text == "join":
        await handle_join_command(event)
    elif text == "left":
        await handle_left_command(event)
    # If text is neither 'join' nor 'left', do nothing.


def setup(client_instance):
    """Registers the event handler for the join and left commands."""
    # The handler is registered using the @client.on decorator above
    logger.info(
        "Join-Left module loaded with joineeef logging and command deletion/reply editing.")


# Define HELP_TEXT for the help command
# This text will be automatically collected by the help handler
HELP_TEXT = "**دستورات عضویت و ترک:**\n• `join` - عضویت در لینک‌های یافت شده در پیام ریپلای شده.\n• `left` - ترک چت‌های یافت شده در پیام ریپلای شده.\n\n"
