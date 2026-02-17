# modules/auto_clearer.py
# Automatically deletes messages based on type (pic, txt, vid, file, media) in bot chats only.
# Can be controlled globally via Saved Messages or per-bot in the bot's chat.
# Commands:
# - autoclear <type> <on/off> <1/2/3> (in Saved Messages or bot chat) -> Sets filter, applies to past messages, and enables future deletion
# - autoclear status (in Saved Messages only)

import asyncio
import logging
import json
import os
import re
from telethon import events, errors
from telethon.tl.types import (
    MessageMediaPhoto,
    DocumentAttributeVideo,
    DocumentAttributeSticker,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    User,
    ReplyInlineMarkup,
    KeyboardButtonUrl
)
from telethon.utils import get_display_name
from client import client
from config import SESSION_FILENAME, HISTORY_LIMIT
from helpers.utils import is_photo, get_file_extension, safe_delete

logger = logging.getLogger(__name__)

# --- Configuration ---
SETTINGS_FILE = "autoclear_settings.json"  # File to store settings

# --- Default settings for auto-clearer ---
# Each filter type now has a 'state' (on/off) and a 'scope' (1: bot, 2: user, 3: both)
DEFAULT_AUTO_CLEAR_SETTINGS = {
    "pic": {"state": False, "scope": 3},
    "txt": {"state": False, "scope": 3},
    "vid": {"state": False, "scope": 3},
    "file": {"state": False, "scope": 3},
    # New filter type: media (all media except files)
    "media": {"state": False, "scope": 3},
}

# --- Global settings for auto-clearer (applies if bot-specific settings are not set) ---
GLOBAL_AUTO_CLEAR_SETTINGS = DEFAULT_AUTO_CLEAR_SETTINGS.copy()

# --- Bot-specific settings (overrides global settings for specific bots) ---
# Structure: { bot_id: { "pic": { "state": bool, "scope": int }, ... }, ... }
BOT_SPECIFIC_SETTINGS = {}

# --- Cache for user/chat entities to reduce API calls ---
ENTITY_CACHE = {}
ME_ENTITY = None  # Cache for the user's own entity

# --- Command aliases ---
AUTO_CLEAR_COMMANDS = [
    "autoclear"
]

STATUS_COMMANDS = ["status"]
ON_COMMANDS = ["on"]
OFF_COMMANDS = ["off"]
SCOPE_COMMANDS = {
    "1": 1,
    "2": 2,
    "3": 3
}
TYPE_COMMANDS = {
    "pic": "pic",
    "txt": "txt",
    "vid": "vid",
    "file": "file",
    "media": "media"
}


# --- Load settings from file ---
def load_auto_clear_settings():
    """Loads auto-clear settings from a JSON file."""
    global GLOBAL_AUTO_CLEAR_SETTINGS, BOT_SPECIFIC_SETTINGS
    settings_path = os.path.join(
        os.path.dirname(SESSION_FILENAME), SETTINGS_FILE)
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                loaded_settings = json.load(f)

            # Load global settings
            global_settings = loaded_settings.get("global", {})
            merged_global = DEFAULT_AUTO_CLEAR_SETTINGS.copy()
            merged_global.update(global_settings)
            # Ensure all keys have the correct structure
            for key in DEFAULT_AUTO_CLEAR_SETTINGS:
                if key not in merged_global:
                    merged_global[key] = DEFAULT_AUTO_CLEAR_SETTINGS[key].copy()
                else:
                    # Ensure 'state' and 'scope' keys exist, defaulting if missing
                    if "state" not in merged_global[key]:
                        merged_global[key]["state"] = DEFAULT_AUTO_CLEAR_SETTINGS[key]["state"]
                    if "scope" not in merged_global[key]:
                        merged_global[key]["scope"] = DEFAULT_AUTO_CLEAR_SETTINGS[key]["scope"]
            GLOBAL_AUTO_CLEAR_SETTINGS = merged_global

            # Load bot-specific settings
            bot_settings = loaded_settings.get("bots", {})
            # Validate bot settings structure
            validated_bot_settings = {}
            for bot_id_str, settings in bot_settings.items():
                try:
                    bot_id = int(bot_id_str)
                    merged_bot = DEFAULT_AUTO_CLEAR_SETTINGS.copy()
                    merged_bot.update(settings)
                    # Ensure all keys have the correct structure for this bot
                    for key in DEFAULT_AUTO_CLEAR_SETTINGS:
                        if key not in merged_bot:
                            merged_bot[key] = DEFAULT_AUTO_CLEAR_SETTINGS[key].copy()
                        else:
                            # Ensure 'state' and 'scope' keys exist, defaulting if missing
                            if "state" not in merged_bot[key]:
                                merged_bot[key]["state"] = DEFAULT_AUTO_CLEAR_SETTINGS[key]["state"]
                            if "scope" not in merged_bot[key]:
                                merged_bot[key]["scope"] = DEFAULT_AUTO_CLEAR_SETTINGS[key]["scope"]
                    validated_bot_settings[bot_id] = merged_bot
                except (ValueError, TypeError):
                    logger.warning(f"Invalid bot ID in settings: {bot_id_str}")

            BOT_SPECIFIC_SETTINGS = validated_bot_settings
            logger.info(f"Auto-clear settings loaded from {settings_path}.")
        except Exception as e:
            logger.error(
                f"Failed to load auto-clear settings from {settings_path}: {repr(e)}. Using defaults.")
            GLOBAL_AUTO_CLEAR_SETTINGS = DEFAULT_AUTO_CLEAR_SETTINGS.copy()
            BOT_SPECIFIC_SETTINGS = {}
    else:
        logger.info(
            f"Auto-clear settings file {settings_path} not found. Using defaults.")
        GLOBAL_AUTO_CLEAR_SETTINGS = DEFAULT_AUTO_CLEAR_SETTINGS.copy()
        BOT_SPECIFIC_SETTINGS = {}

# --- Save settings to file ---


def save_auto_clear_settings():
    """Saves current auto-clear settings to a JSON file."""
    settings_path = os.path.join(
        os.path.dirname(SESSION_FILENAME), SETTINGS_FILE)
    try:
        data_to_save = {
            "global": GLOBAL_AUTO_CLEAR_SETTINGS,
            # Convert bot_id to string for JSON
            "bots": {str(k): v for k, v in BOT_SPECIFIC_SETTINGS.items()}
        }
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, ensure_ascii=False, indent=4)
        logger.debug(f"Auto-clear settings saved to {settings_path}.")
    except Exception as e:
        logger.error(
            f"Failed to save auto-clear settings to {settings_path}: {repr(e)}")

# --- Get effective settings for a specific bot ---


def get_bot_settings(bot_id):
    """Returns the effective settings for a given bot ID, using bot-specific or global settings."""
    return BOT_SPECIFIC_SETTINGS.get(bot_id, GLOBAL_AUTO_CLEAR_SETTINGS)

# --- Check if a message contains media that is NOT a file ---


def message_is_non_file_media(msg):
    """Checks if a message contains media that is NOT a file (e.g., photo, vid, sticker, audio note, etc.)."""
    if not msg.media:
        return False  # No media at all

    # Check if it's a photo (including GIFs sent as MessageMediaPhoto)
    if is_photo(msg.media):
        return True

    # Check if it's a document (potential file or other media types like video/gif/sticker/audio)
    if hasattr(msg.media, 'document') and msg.media.document:
        # Check for specific non-file attributes first
        for attr in msg.media.document.attributes:
            if isinstance(attr, (DocumentAttributeVideo, DocumentAttributeSticker, DocumentAttributeAudio)):
                # It's a video, sticker, or audio (not a general file)
                return True

        # If it has DocumentAttributeFilename, it's likely a file
        has_filename_attr = any(isinstance(attr, DocumentAttributeFilename)
                                for attr in msg.media.document.attributes)
        if not has_filename_attr:
            # It's a document but doesn't have a filename attr, likely a non-standard media or unsupported format
            # Treat this as non-file media for the purpose of 'media' filter
            return True
        else:
            # It's a document with a filename attr -> it's a file
            return False

    # If it has media but is not a photo and not a document, it might be MessageMediaGeo, MessageMediaContact, etc.
    # These are not files, so treat them as non-file media.
    return True

# --- Check if a message matches a specific filter type and scope ---


def message_matches_filter(msg, filter_type, scope):
    """Checks if a message matches the specified filter type and scope (1: bot, 2: user, 3: both)."""
    # First, check if the message type matches the filter
    type_match = False
    if filter_type == "txt":
        # Text-only: has text, no media
        type_match = bool(msg.message and not msg.media)
    elif filter_type == "pic":
        # Photo: use the helper function which checks MessageMediaPhoto and document attributes
        type_match = msg.media is not None and is_photo(msg.media)
        # Check for image stickers sent as documents (DocumentAttributeSticker and no DocumentAttributeVideo)
        if not type_match and msg.media and hasattr(msg.media, 'document') and msg.media.document:
            has_sticker_attr = False
            has_video_attr = False
            for attr in msg.media.document.attributes:
                if isinstance(attr, DocumentAttributeSticker):
                    has_sticker_attr = True
                if isinstance(attr, DocumentAttributeVideo):
                    has_video_attr = True
            # If it's a sticker document and NOT a video/gif sticker, consider it a pic
            if has_sticker_attr and not has_video_attr:
                type_match = True
    elif filter_type == "vid":
        # Video/GIF: check document attributes for DocumentAttributeVideo
        if msg.media and hasattr(msg.media, 'document') and msg.media.document:
            for attr in msg.media.document.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    type_match = True
                    break
    elif filter_type == "file":
        # File: has media, is not a photo, is not a video/gif, and is a document with filename attr
        if msg.media:
            # Exclude photos (including GIFs sent as photos via MessageMediaPhoto)
            if is_photo(msg.media):
                type_match = False
            # Exclude videos/gifs
            elif hasattr(msg.media, 'document') and msg.media.document:
                for attr in msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        type_match = False
                        break
                # Only runs if the inner loop did NOT break (no video attr found)
                else:
                    # Check if it has a filename attribute, indicating it's a file
                    has_filename_attr = any(isinstance(
                        attr, DocumentAttributeFilename) for attr in msg.media.document.attributes)
                    # If it's a document and has a filename attr (and passed video/photo checks), it's a file
                    if has_filename_attr:
                        type_match = True
    elif filter_type == "media":
        # Media (non-file): use the new helper function
        type_match = message_is_non_file_media(msg)

    if not type_match:
        return False

    # Second, check if the message sender matches the scope
    # Scope 1: Only messages FROM the bot (received messages)
    # Scope 2: Only messages FROM the user (outgoing messages)
    # Scope 3: Both messages FROM the bot AND FROM the user
    if scope == 1:
        return not msg.out  # Message is from bot (received)
    elif scope == 2:
        return msg.out  # Message is from user (sent)
    elif scope == 3:
        return True  # Message is from either bot or user
    else:
        # Should not happen if called correctly, but default to False
        logger.warning(f"Invalid scope {scope} in message_matches_filter.")
        return False

# --- Function to clear past messages based on current settings ---


async def clear_past_messages(target_entity, settings_dict, limit=HISTORY_LIMIT):
    """Clears past messages in a target entity based on the provided settings dictionary."""
    deleted_count = 0
    # Collect message IDs to delete in batches
    ids_to_delete = []
    batch_size = 100  # Maximum allowed by Telegram API

    async for msg in client.iter_messages(target_entity, limit=limit):
        if msg is None:
            continue
        # Check each active filter in the settings dictionary
        for filter_type, config in settings_dict.items():
            if config["state"]:  # If the filter type is enabled
                scope = config["scope"]
                if message_matches_filter(msg, filter_type, scope):
                    ids_to_delete.append(msg.id)
                    break  # Avoid deleting the same message multiple times if multiple filters match

    # Delete messages in batches
    for i in range(0, len(ids_to_delete), batch_size):
        batch = ids_to_delete[i:i + batch_size]
        try:
            await client.delete_messages(target_entity, batch)
            deleted_count += len(batch)
            logger.debug(
                f"Deleted batch of {len(batch)} past messages in {target_entity.id}.")
        except errors.FloodWaitError as e:
            logger.warning(
                f"FloodWaitError during batch delete: {e.seconds}s. Waiting...")
            await asyncio.sleep(e.seconds)
            # Retry the batch once after the wait
            try:
                await client.delete_messages(target_entity, batch)
                deleted_count += len(batch)
                logger.debug(
                    f"Retried and deleted batch of {len(batch)} past messages in {target_entity.id}.")
            except Exception as e2:
                logger.error(f"Failed to delete batch after retry: {repr(e2)}")
        except Exception as e:
            logger.error(
                f"Failed to delete batch of messages in {target_entity.id}: {repr(e)}")

    return deleted_count

# --- Event Handler for incoming messages (auto-delete logic) ---


@client.on(events.NewMessage(incoming=True))
async def on_new_incoming(event):
    """Handles auto-deletion of incoming messages based on settings."""
    msg = event.message
    if msg is None:
        return

    # Use cached chat info if available, otherwise fetch and cache
    chat_id = event.chat_id
    if chat_id not in ENTITY_CACHE:
        try:
            chat = await event.get_chat()
            if isinstance(chat, User) and getattr(chat, "bot", False):
                ENTITY_CACHE[chat_id] = chat
            else:
                return  # Not a bot chat, ignore
        except Exception as e:
            logger.error(
                f"Could not get chat for incoming event {event.id}: {repr(e)}")
            return
    else:
        chat = ENTITY_CACHE[chat_id]
        if not (isinstance(chat, User) and getattr(chat, "bot", False)):
            return  # Cached entity is not a bot chat, ignore

    # Get effective settings for this bot
    effective_settings = get_bot_settings(chat.id)

    # Check each filter type against the message and settings
    for filter_type, config in effective_settings.items():
        if config["state"]:  # If the filter type is enabled
            scope = config["scope"]
            # Scope 1 (bot) or 3 (both) applies to incoming messages
            if scope in [1, 3] and message_matches_filter(msg, filter_type, scope):
                logger.info(
                    f"Auto-deleting {filter_type} (scope {scope}) incoming message from bot {chat.id} based on settings.")
                if await safe_delete(client, event.chat_id, msg.id):
                    logger.debug(
                        f"Deleted {filter_type} (scope {scope}) incoming message {msg.id} from {chat.id}")
                # Break after first match to avoid deleting the same message multiple times
                break

# --- Event Handler for outgoing messages (auto-delete logic for sent messages) ---


@client.on(events.NewMessage(outgoing=True))
async def on_new_outgoing(event):
    """Handles auto-deletion of outgoing messages based on settings."""
    msg = event.message
    if msg is None:
        return

    # Use cached chat info if available, otherwise fetch and cache
    chat_id = event.chat_id
    if chat_id not in ENTITY_CACHE:
        try:
            chat = await event.get_chat()
            if isinstance(chat, User) and getattr(chat, "bot", False):
                ENTITY_CACHE[chat_id] = chat
            else:
                return  # Not in a bot chat, ignore
        except Exception as e:
            logger.error(
                f"Could not get chat for outgoing event {event.id}: {repr(e)}")
            return
    else:
        chat = ENTITY_CACHE[chat_id]
        if not (isinstance(chat, User) and getattr(chat, "bot", False)):
            return  # Cached entity is not a bot chat, ignore

    # Get effective settings for this bot
    effective_settings = get_bot_settings(chat.id)

    # Check each filter type against the message and settings
    for filter_type, config in effective_settings.items():
        if config["state"]:  # If the filter type is enabled
            scope = config["scope"]
            # Scope 2 (user) or 3 (both) applies to outgoing messages
            if scope in [2, 3] and message_matches_filter(msg, filter_type, scope):
                logger.info(
                    f"Auto-deleting {filter_type} (scope {scope}) outgoing message to bot {chat.id} based on settings.")
                if await safe_delete(client, event.chat_id, msg.id):
                    logger.debug(
                        f"Deleted {filter_type} (scope {scope}) outgoing message {msg.id} to {chat.id}")
                # Break after first match to avoid deleting the same message multiple times
                break

# --- Event Handler for outgoing messages (command handling) ---


@client.on(events.NewMessage(outgoing=True))
async def handle_auto_clear_commands(event):
    """Handles all autoclear commands."""
    text = (event.raw_text or "").strip()

    # Check if command starts with any of the defined autoclear commands
    command_found = None
    for cmd in AUTO_CLEAR_COMMANDS:
        if text.lower().startswith(cmd.lower()):
            command_found = cmd
            break

    if not command_found:
        return  # No command matched

    # Extract remaining text after the command
    remaining_text = text[len(command_found):].strip()
    cmd_parts = [command_found] + remaining_text.split()

    # Get user's own entity for Saved Messages check (use cached value if available)
    global ME_ENTITY
    if ME_ENTITY is None:
        ME_ENTITY = await client.get_me()
    is_in_saved_messages = (event.chat_id == ME_ENTITY.id)

    # --- Handle 'autoclear status' (only in Saved Messages) ---
    if len(cmd_parts) >= 2 and cmd_parts[1].lower() in STATUS_COMMANDS:
        if not is_in_saved_messages:
            logger.debug(
                "autoclear status command ignored - not in Saved Messages.")
            return
        await _handle_autoclear_status(event)
        return

    # --- Handle 'autoclear <type> <on/off> <scope>' ---
    if len(cmd_parts) == 4:
        raw_type = cmd_parts[1].lower()
        raw_action = cmd_parts[2].lower()
        raw_scope = cmd_parts[3].lower()

        # Map aliases to standard values
        cmd_type = TYPE_COMMANDS.get(raw_type)
        if cmd_type not in DEFAULT_AUTO_CLEAR_SETTINGS:
            await event.edit(f"❌ Invalid type: {raw_type}. Valid types: pic, txt, vid, file, media")
            return

        if raw_action in ON_COMMANDS:
            cmd_action = "on"
        elif raw_action in OFF_COMMANDS:
            cmd_action = "off"
        else:
            await event.edit("❌ Invalid action. Use 'on' or 'off'.")
            return

        try:
            cmd_scope = SCOPE_COMMANDS.get(raw_scope)
            if cmd_scope not in [1, 2, 3]:
                await event.edit("❌ Invalid scope. Use 1 (bot), 2 (user), or 3 (both).")
                return
        except ValueError:
            await event.edit("❌ Invalid scope. Use 1 (bot), 2 (user), or 3 (both).")
            return

        # Determine target: Saved Messages = global, Bot chat = specific bot
        # Use cached chat info if available, otherwise fetch and cache
        target_chat_id = event.chat_id
        if target_chat_id not in ENTITY_CACHE:
            try:
                target_chat = await event.get_chat()
                ENTITY_CACHE[target_chat_id] = target_chat
            except Exception as e:
                logger.error(
                    f"Could not get chat for command event {event.id}: {repr(e)}")
                return
        else:
            target_chat = ENTITY_CACHE[target_chat_id]

        if isinstance(target_chat, User) and getattr(target_chat, "bot", False):
            # Command sent in a bot's chat -> apply to this bot
            target_bot_id = target_chat.id
            settings_dict = BOT_SPECIFIC_SETTINGS.setdefault(
                target_bot_id, DEFAULT_AUTO_CLEAR_SETTINGS.copy())
            settings_dict[cmd_type]["state"] = (cmd_action == "on")
            settings_dict[cmd_type]["scope"] = cmd_scope
            logger.info(
                f"Set autoclear {cmd_type} for bot {target_bot_id} to {cmd_action} (scope {cmd_scope}).")
            status_text = f"✅ Auto-clear {cmd_type} for this bot is now {'enabled' if cmd_action == 'on' else 'disabled'} (scope {cmd_scope})."
            effective_settings_for_past = settings_dict
            target_entity_for_past = target_chat
        elif is_in_saved_messages:
            # Command sent in Saved Messages -> apply globally
            GLOBAL_AUTO_CLEAR_SETTINGS[cmd_type]["state"] = (
                cmd_action == "on")
            GLOBAL_AUTO_CLEAR_SETTINGS[cmd_type]["scope"] = cmd_scope
            logger.info(
                f"Set global autoclear {cmd_type} to {cmd_action} (scope {cmd_scope}).")
            status_text = f"✅ Global auto-clear {cmd_type} is now {'enabled' if cmd_action == 'on' else 'disabled'} (scope {cmd_scope})."
            effective_settings_for_past = GLOBAL_AUTO_CLEAR_SETTINGS
            # Indicate past clearing should happen for all bots
            target_entity_for_past = "all_bots"
        else:
            # Command sent in a group/channel or non-bot private chat
            await event.edit("ℹ️ This command can only be used in Saved Messages or in a bot's chat.")
            return

        # Save settings after modification
        save_auto_clear_settings()

        # Clear past messages based on the *new* setting if it's 'on'
        if cmd_action == "on":
            processing_msg = await event.edit(f"🗑️ Clearing past {cmd_type} messages (scope {cmd_scope})...")
            total_past_deleted = 0
            if target_entity_for_past == "all_bots":
                # Iterate through all dialogs and clear for bots
                async for dialog in client.iter_dialogs():
                    entity = dialog.entity
                    if isinstance(entity, User) and getattr(entity, "bot", False):
                        # Use potentially bot-specific settings for this specific bot
                        # If bot has specific settings, use them for the specific type; otherwise, use global
                        bot_settings = BOT_SPECIFIC_SETTINGS.get(entity.id, {})
                        # Use the specific type's setting from global if not set for bot
                        type_setting_to_use = bot_settings.get(
                            cmd_type, GLOBAL_AUTO_CLEAR_SETTINGS[cmd_type])
                        deleted_in_chat = await clear_past_messages(entity, {cmd_type: type_setting_to_use})
                        total_past_deleted += deleted_in_chat
            else:
                # Clear for the specific bot chat
                deleted_in_chat = await clear_past_messages(target_entity_for_past, {cmd_type: effective_settings_for_past[cmd_type]})
                total_past_deleted = deleted_in_chat

            await processing_msg.edit(f"✅ Cleared {total_past_deleted} past {cmd_type} messages (scope {cmd_scope}). Auto-clear is now {'enabled' if cmd_action == 'on' else 'disabled'} (scope {cmd_scope}).")
        else:
            # If turned 'off', just confirm the setting change
            await event.edit(status_text)

        return

    # If command doesn't match known patterns
    await event.edit("❌ Invalid command format. Use:\n- `autoclear <type> <on/off> <1/2/3>`\n- `autoclear status`")


async def _handle_autoclear_status(event):
    """Handles the 'autoclear status' command."""
    status_lines = ["📊 **Auto-Clear Status:**"]
    status_lines.append("\n**Global Settings:**")
    for key, config in GLOBAL_AUTO_CLEAR_SETTINGS.items():
        state = "✅ ON" if config["state"] else "❌ OFF"
        scope = config["scope"]
        scope_desc = {1: "Bot", 2: "User", 3: "Both"}[scope]
        status_lines.append(f"  • `{key}`: {state} (Scope: {scope_desc})")

    if BOT_SPECIFIC_SETTINGS:
        status_lines.append("\n**Bot-Specific Settings (Active Only):**")
        # Filter bots that have at least one active filter (state: True)
        active_bot_specific_settings = {bot_id: settings for bot_id, settings in BOT_SPECIFIC_SETTINGS.items(
        ) if any(cfg["state"] for cfg in settings.values())}
        for bot_id, settings in active_bot_specific_settings.items():
            try:
                # Use cached entity if available
                if bot_id in ENTITY_CACHE:
                    bot_entity = ENTITY_CACHE[bot_id]
                else:
                    bot_entity = await client.get_entity(bot_id)
                    ENTITY_CACHE[bot_id] = bot_entity  # Cache it
                bot_name = get_display_name(bot_entity)
            except Exception:
                # Fallback if entity can't be fetched
                bot_name = f"ID {bot_id}"

            # Get only active configs for this bot
            active_configs = {k: v for k, v in settings.items() if v["state"]}
            if active_configs:  # Double-check it has active configs before adding
                # Use tg://user?id=BOT_ID to create a clickable link to the bot chat
                status_lines.append(
                    f"  • **{bot_name}** ([ID: {bot_id}](tg://user?id={bot_id})):")
                for k, v in active_configs.items():
                    scope_desc = {1: "Bot", 2: "User", 3: "Both"}[v["scope"]]
                    status_lines.append(
                        f"    - `{k}`: ✅ ON (Scope: {scope_desc})")

    full_status = "\n".join(status_lines)
    # Ensure Markdown is parsed for the link
    await event.edit(full_status, parse_mode='Markdown')
    logger.debug("Autoclear status command executed and message edited.")


def setup(client_instance):
    """Registers the event handlers and loads settings."""
    # Load settings when module is set up
    load_auto_clear_settings()
    logger.info(
        "Auto-Clearer module loaded with persistent settings, new scope logic, 'media' filter, and 'autoclear all' removed.")


# Define HELP_TEXT for the help command
HELP_TEXT = "**دستورات پاک‌سازی خودکار (autoclear):**\n• `autoclear <type> <on/off> <1/2/3>` - روشن/خاموش کردن پاک‌سازی خودکار انواع پیام. عدد 1 فقط پیام‌های ربات، 2 فقط پیام‌های شما، 3 هر دو. اگر در پیام‌های ذخیره شده فرستاده شود برای همه ربات‌ها اعمال می‌شود، در غیر اینصورت فقط برای ربات فعلی. (type: pic, txt, vid, file, media)\n• `autoclear status` - نمایش وضعیت فعلی تنظیمات کلی و ربات‌های خاص.\n\n"
