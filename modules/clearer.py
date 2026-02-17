# modules/clearer.py
# Handles the 'clear' command logic for deleting messages based on filters.

import asyncio
import logging
import time
from collections import defaultdict
from telethon import events, errors
from telethon.tl.types import (
    DocumentAttributeVideo,
    DocumentAttributeSticker,
    MessageMediaPhoto
)
from helpers.utils import safe_delete, get_file_extension, is_photo, contains_any_link
from config import HISTORY_LIMIT
from client import client

logger = logging.getLogger(__name__)

# کش جهانی برای اطلاعات فرستنده
SENDER_CACHE = {}
CACHE_TTL = 300  # 5 دقیقه


async def is_bot_cached(msg):
    """بررسی ربات بودن فرستنده با کش کردن نتیجه"""
    if not msg.sender_id:
        return False

    current_time = time.time()
    if msg.sender_id in SENDER_CACHE:
        cached_time, is_bot = SENDER_CACHE[msg.sender_id]
        if current_time - cached_time < CACHE_TTL:
            return is_bot

    try:
        sender = await msg.get_sender()
        is_bot = getattr(sender, "bot", False)
        SENDER_CACHE[msg.sender_id] = (current_time, is_bot)
        return is_bot
    except Exception:
        return False


async def batch_delete_messages(client, chat_entity, message_ids, batch_size=100):
    """حذف گروهی پیام‌ها برای کاهش تعداد درخواست‌ها"""
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i:i + batch_size]
        try:
            await client.delete_messages(chat_entity, batch)
            logger.debug(f"Deleted batch of {len(batch)} messages")
        except Exception as e:
            logger.error(f"Batch delete failed: {e}")
            # اگر گروهی شکست خورد، تک‌تک امتحان کن
            for msg_id in batch:
                await safe_delete(client, chat_entity, msg_id)


def should_check_message(msg, active_filters):
    """بررسی اولیه آیا پیام باید کاملاً بررسی شود یا نه"""
    # اگر فیلتر txt یا media وجود داشته باشد، بررسی کن
    if "txt" in active_filters and not msg.message:
        return False
    if "media" in active_filters and not msg.media:
        return False
    if "self" in active_filters and not msg.out:
        return False
    return True


@client.on(events.NewMessage(outgoing=True))
async def handle_clear_command(event):
    start_time = time.time()
    original_text = (event.raw_text or "").strip()

    # Check if the message starts with 'clear'
    if not original_text.startswith("clear"):
        return

    # Split the command text into parts
    parts = original_text.split()
    # Check if only 'clear' is provided (no additional parameters)
    if len(parts) == 1:  # فقط 'clear'
        # This is the specific 'clear' command -> delete text-only messages (including links)
        chat_entity = event.chat_id
        logger.info("Clearing text-only messages (including links)...")

        deleted_count = 0
        messages_to_delete = []

        async for msg in client.iter_messages(chat_entity, limit=HISTORY_LIMIT):
            if msg is None or msg.id == event.message.id:
                continue
            # Check if message is text-only: has text and no media (links are in text)
            if msg.message and not msg.media:
                messages_to_delete.append(msg.id)

                # حذف گروهی هر 50 پیام
                if len(messages_to_delete) >= 50:
                    await batch_delete_messages(client, chat_entity, messages_to_delete[:50])
                    deleted_count += 50
                    messages_to_delete = messages_to_delete[50:]

        # حذف باقی‌مانده
        if messages_to_delete:
            await batch_delete_messages(client, chat_entity, messages_to_delete)
            deleted_count += len(messages_to_delete)

        # ادیت پیام اصلی و حذف خودکار
        end_time = time.time()
        duration = end_time - start_time
        await event.edit(f"✅ {deleted_count} پیام متنی حذف شد\n⏱ زمان اجرا: {duration:.2f} ثانیه")

        # حذف پیام بعد از 2 ثانیه
        await asyncio.sleep(2)
        try:
            await event.delete()
        except Exception:
            pass

        logger.info(
            f"Clear done. {deleted_count} text messages deleted in {duration:.2f}s.")
        return  # Exit after handling specific 'clear'

    # If there are parameters (e.g., 'clear all', 'clear txt', 'clear pic file')
    # The first part is always 'clear', so we process the rest
    # e.g., ["vid", "pic"], ["pic", "link"], ["all"], ["self"], ["bot"], etc.
    command_parts = parts[1:]

    # Define valid command parts (removed "link", added "self", "bot", "txt")
    valid_parts = {
        "all": "all",
        "media": "media",
        "file": "file",
        "vid": "vid",
        "pic": "pic",
        # Added: 'txt' for text-only messages (includes links now)
        "txt": "txt",
        # Added: 'self' for messages sent by the user
        "self": "self",
        # Added: 'bot' for messages sent by bots
        "bot": "bot",
    }

    # Determine which parts are valid
    active_filters = set()
    file_extensions_include = set()  # For formats like (pdf)(zip)
    file_extensions_exclude = set()  # For formats like [pdf][zip]
    for part in command_parts:
        # Check for file extensions in parentheses (include)
        if part.startswith('(') and part.endswith(')'):
            ext = part[1:-1].lower()
            if ext:  # Ensure it's not empty
                file_extensions_include.add(ext)
        # Check for file extensions in square brackets (exclude)
        elif part.startswith('[') and part.endswith(']'):
            ext = part[1:-1].lower()
            if ext:  # Ensure it's not empty
                file_extensions_exclude.add(ext)
        # Check for standard filters (including new 'self', 'bot')
        elif part in valid_parts:
            active_filters.add(valid_parts[part])
        else:
            # If an invalid part is found, ignore just the invalid part.
            logger.debug(
                f"[clear-command] ignoring unknown part: '{part}' in '{original_text}'")

    # If no valid filters are found and no specific extensions are set, do nothing
    if not active_filters and not file_extensions_include and not file_extensions_exclude:
        logger.debug(
            f"[clear-command] no valid filters found in '{original_text}', doing nothing.")
        return

    chat_entity = event.chat_id
    logger.debug(
        f"[clear-command] filters {sorted(active_filters)}, inc {sorted(file_extensions_include)}, exc {sorted(file_extensions_exclude)} in chat {chat_entity}; scanning up to {HISTORY_LIMIT} messages")

    # تعیین آیا نیاز به بررسی فرستنده وجود دارد
    needs_sender_check = "bot" in active_filters

    # لیست پیام‌هایی که باید حذف شوند
    messages_to_delete = []

    # Iterate messages in the chat
    async for msg in client.iter_messages(chat_entity, limit=HISTORY_LIMIT):
        # skip service messages or None
        if msg is None:
            continue
        # Skip messages that are the command message itself until after sweep
        if msg.id == event.message.id:
            continue

        try:
            # Determine if this message matches any of the active filters
            should_delete = False
            for filter_type in active_filters:
                if filter_type == "all":
                    # If 'all' is one of the filters, match everything (except command itself, handled above)
                    should_delete = True
                    break  # No need to check other filters if 'all' is present
                elif filter_type == "media":
                    if msg.media is not None:
                        should_delete = True
                        break
                elif filter_type == "file":
                    if msg.media is not None:
                        is_file = True
                        if is_photo(msg.media):
                            is_file = False
                        elif hasattr(msg.media, 'document') and msg.media.document:
                            for attr in msg.media.document.attributes:
                                if isinstance(attr, (DocumentAttributeVideo, DocumentAttributeSticker)):
                                    is_file = False
                                    break
                            if is_file:
                                # If include list is set, only delete if extension matches
                                if file_extensions_include:
                                    ext = get_file_extension(msg.media)
                                    # ext[1:] removes the dot
                                    if ext and ext[1:] in file_extensions_include:
                                        should_delete = True
                                        break
                                # If exclude list is set, delete if extension does NOT match any in the list
                                elif file_extensions_exclude:
                                    ext = get_file_extension(msg.media)
                                    # ext[1:] removes the dot
                                    if not ext or ext[1:] not in file_extensions_exclude:
                                        should_delete = True
                                        break
                                # If neither list is set, just delete the file
                                else:
                                    should_delete = True
                                    break
                elif filter_type == "vid":
                    if msg.media is not None and hasattr(msg.media, 'document') and msg.media.document:
                        for attr in msg.media.document.attributes:
                            if isinstance(attr, DocumentAttributeVideo):
                                should_delete = True
                                break
                        if should_delete:
                            break
                elif filter_type == "pic":
                    if msg.media is not None and is_photo(msg.media):
                        should_delete = True
                        break
                # Added: 'txt' filter for text-only messages (includes links)
                elif filter_type == "txt":
                    # Check if message has text content and no media
                    # This means messages with text AND links will be caught here
                    if msg.message and not msg.media:
                        should_delete = True
                        break
                # Added: 'self' filter for messages sent by the user
                elif filter_type == "self":
                    if msg.out:  # Message was sent by the user
                        should_delete = True
                        break
                # Added: 'bot' filter for messages sent by bots
                elif filter_type == "bot":
                    # Get sender and check if it's a bot - با کش
                    if await is_bot_cached(msg):
                        should_delete = True
                        break

            if should_delete:
                messages_to_delete.append(msg.id)

                # حذف گروهی هر 50 پیام
                if len(messages_to_delete) >= 50:
                    await batch_delete_messages(client, chat_entity, messages_to_delete[:50])
                    messages_to_delete = messages_to_delete[50:]

        except Exception as e:
            # If a particular deletion fails, do nothing for that message.
            logger.error(
                f"[clear-command] exception handling message {msg.id}: {repr(e)}")
            continue

    # حذف باقی‌مانده
    if messages_to_delete:
        await batch_delete_messages(client, chat_entity, messages_to_delete)

    # ادیت پیام اصلی و حذف خودکار
    end_time = time.time()
    duration = end_time - start_time
    await event.edit(f"✅ {len(messages_to_delete)} پیام حذف شد\n⏱ زمان اجرا: {duration:.2f} ثانیه")

    # حذف پیام بعد از 2 ثانیه
    await asyncio.sleep(2)
    try:
        await event.delete()
    except Exception:
        pass

    logger.info(
        f"Clear command completed. {len(messages_to_delete)} messages deleted in {duration:.2f}s.")


def setup(client_instance):
    """Setup function called by the module loader."""
    # The event handler is already registered using the decorator @client.on
    # This function can be used for any additional setup if needed in the future.
    logger.info("Clearer module loaded.")
    pass


# Define HELP_TEXT for the help command
HELP_TEXT = "**دستورات پاک‌سازی (clear):**\n• `clear` - پاک کردن پیام‌های متنی \n• `clear txt` - پاک کردن پیام‌های متنی  \n• `clear all` - پاک کردن تمام پیام‌های شما\n• `clear media` - پاک کردن تمام پیام‌های دارای رسانه\n• `clear file` - پاک کردن فقط فایل‌ها\n• `clear vid` - پاک کردن فقط ویدیو/گیف\n• `clear pic` - پاک کردن فقط عکس\n• `clear self` - پاک کردن پیام‌های ارسالی توسط شما\n• `clear bot` - پاک کردن پیام‌های ارسالی توسط ربات‌ها\n\n"
