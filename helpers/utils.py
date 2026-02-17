# helpers/utils.py
# Contains common utility functions used across different modules of the userbot.

import asyncio # برای asyncio.iscoroutine
import math     # برای تابع get_file_size
import logging # برای logger
import re       # برای تابع contains_any_link
from telethon import errors
from telethon.tl.types import (
    DocumentAttributeFilename, # برای get_file_extension
    DocumentAttributeVideo,    # برای get_media_info
    DocumentAttributeSticker,  # برای get_media_info
    MessageMediaPhoto          # برای is_photo
)
# نیازی به import client از client نیست، چون client به عنوان آرگومان به safe_delete داده می‌شود.
# اگر ensure_awaitable در utils.py تعریف شده باشد، نیازی به import ندارد.
# اگر در جای دیگری تعریف شده و در utils استفاده می‌شود، باید وارد شود.
# فرض بر این است که ensure_awaitable در این فایل تعریف شده (همانطور که در کد نهایی بود).

logger = logging.getLogger(__name__)

# ---------- Helper: awaitable checker ----------
async def ensure_awaitable(coro_or_value):
    """
    Ensures the return value is awaited if it's a coroutine.
    This helps handle differences between Telethon versions where some methods might be sync/async.
    """
    if asyncio.iscoroutine(coro_or_value):
        return await coro_or_value
    return coro_or_value

# ---------- Helper: safe delete ----------
async def safe_delete(client_instance, entity, message_ids):
    """
    Attempt to delete message(s). Swallows exceptions so we "do nothing" if not possible.
    message_ids: int or list[int]
    """
    try:
        await client_instance.delete_messages(entity, message_ids, revoke=True)
        return True
    except (errors.rpcerrorlist.MessageDeleteForbiddenError,
            errors.rpcerrorlist.ChatAdminRequiredError,
            errors.FloodWaitError,
            errors.rpcerrorlist.UserAdminInvalidError,
            errors.rpcerrorlist.ChatWriteForbiddenError,
            errors.RPCError) as e:
        # deletion not possible or rate-limited — treat as "do nothing"
        logger.debug(f"[safe_delete] could not delete {message_ids} in {entity}: {repr(e)}")
        return False
    except Exception as e:
        logger.error(f"[safe_delete] unexpected error deleting {message_ids} in {entity}: {repr(e)}")
        return False

# ---------- Helper: Check if media is a photo (jpg, png, etc.) ----------
def is_photo(media):
    """Check if the media is a photo (jpg, png, etc.)"""
    if isinstance(media, MessageMediaPhoto):
        return True
    # Sometimes photos are sent as documents with image extensions
    if hasattr(media, 'document') and media.document:
        for attr in media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name.lower()
                if filename.endswith(('.jpg', '.jpeg', '.png', '.bmp', '.webp')):
                    # But exclude stickers and gifs which might have these extensions
                    for attr2 in media.document.attributes:
                        if isinstance(attr2, (DocumentAttributeSticker, DocumentAttributeVideo)):
                            return False # It's a sticker or video, not a simple photo
                    return True
    return False

# ---------- Helper: Check if message contains ANY link (Telegram or other) ----------
def contains_any_link(message_text):
    """Check if the message text contains ANY link (Telegram or other)."""
    if not message_text:
        return False
    # Regex pattern to match any URL starting with http:// or https://
    any_link_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    return bool(any_link_pattern.search(message_text))

# ---------- Helper: Get file extension from media ----------
def get_file_extension(media):
    """Extract the file extension from a media object."""
    if hasattr(media, 'document') and media.document:
        for attr in media.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name.lower()
                # Extract extension (e.g., .pdf, .zip)
                parts = filename.rsplit('.', 1)
                if len(parts) == 2:
                    return f".{parts[1]}"
    return None

# ---------- Helper: Get human-readable file size ----------
def get_file_size(size_bytes):
    """Converts bytes to a human-readable format (e.g., KB, MB, GB)."""
    if size_bytes is None:
        return "Unknown"
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"

# ---------- Helper: Get media info ----------
async def get_media_info(media):
    """Extracts detailed information from a media object."""
    info = []
    if hasattr(media, 'document') and media.document:
        doc = media.document
        info.append(f"ID: {doc.id}")
        info.append(f"Access Hash: {doc.access_hash}")
        info.append(f"File Reference: {doc.file_reference}")
        info.append(f"Size: {get_file_size(doc.size)}")
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                info.append(f"Filename: {attr.file_name}")
            elif isinstance(attr, DocumentAttributeVideo):
                info.append(f"Duration: {attr.duration}s")
                info.append(f"Dimensions: {attr.w}x{attr.h}")
                if attr.supports_streaming:
                    info.append("Streaming: Yes")
            elif isinstance(attr, DocumentAttributeSticker):
                info.append(f"Sticker: {attr.alt}")
        # Find general file extension if not in filename attr
        if not any('Filename' in str(a) for a in doc.attributes):
            ext = get_file_extension(media)
            if ext:
                info.append(f"Extension: {ext}")
    elif isinstance(media, MessageMediaPhoto):
        info.append("Type: Photo")
        # Size is usually not available for photos directly, only in doc attrs if sent as doc
    return "\n".join(info)