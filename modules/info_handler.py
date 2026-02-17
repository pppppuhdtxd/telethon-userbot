# modules/info_handler.py
# Handles the 'info' command to display detailed information about a replied message.
# Enhanced to show clickable sender/chat IDs and media type.

import logging
from jdatetime import datetime as jdatetime # Import jdatetime for Persian date conversion
from telethon import events
from telethon.utils import get_display_name
from telethon.tl.types import ( # Import types directly
    DocumentAttributeVideo,
    DocumentAttributeSticker,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    MessageMediaPhoto,
    User, # Import User if needed for type checking
    Chat,
    Channel
)
from helpers.utils import get_file_size, get_media_info, is_photo
from client import client

logger = logging.getLogger(__name__)

def gregorian_to_jalali_with_time(gregorian_dt):
    """Converts a Python datetime object to a Jalali date and time string."""
    try:
        # Convert the datetime object to Tehran timezone first if needed
        # For simplicity, assuming the incoming datetime is UTC and we want Tehran time (+3:30)
        # This is a basic offset addition. A more robust solution uses pytz or zoneinfo.
        import datetime as dt_module
        tehran_offset = dt_module.timedelta(hours=3, minutes=30)
        tehran_time = gregorian_dt + tehran_offset
        # Use jdatetime to convert the Tehran time
        jalali_dt = jdatetime.fromgregorian(datetime=tehran_time)
        # Format as desired, e.g., "1404/08/02 14:30:00"
        jalali_str = jalali_dt.strftime('%Y/%m/%d %H:%M:%S')
        return jalali_str
    except Exception:
        # If conversion fails, return the original datetime string
        return str(gregorian_dt)

@client.on(events.NewMessage(outgoing=True))
async def handle_info_command(event):
    """Displays detailed information about a replied message when 'info' is sent."""
    text = (event.raw_text or "").strip()

    # Handle 'info' command with reply
    if text == "info" and event.is_reply:
        reply_msg = await event.get_reply_message()
        if not reply_msg:
            info_text = "Could not get the replied message."
            await event.edit(info_text)
            logger.debug("Info command: replied message not found.")
            return

        info_lines = []
        info_lines.append(f"**Message ID:** `{reply_msg.id}`")
        # Convert date and time to Jalali (Tehran timezone)
        jalali_datetime = gregorian_to_jalali_with_time(reply_msg.date)
        info_lines.append(f"**Date:** `{jalali_datetime}`")
        info_lines.append(f"**Outgoing:** `{reply_msg.out}`")
        
        # --- Enhanced Media Type Detection ---
        media_type = "N/A"
        if reply_msg.media:
            if is_photo(reply_msg.media):
                 # Check if it's also an animated sticker sent as photo (MessageMediaPhoto) or a GIF sent as photo
                 # This is less common, usually stickers are DocumentAttributeSticker, GIFs are DocumentAttributeVideo
                 # Let's refine: Check for DocumentAttributeSticker or Video within media if it's a doc
                 # is_photo already handles MessageMediaPhoto and some DocumentAttribute cases
                 # If it passes is_photo and has a document with a sticker attr, it's an animated sticker photo
                 # If it passes is_photo and has no specific video/sticker attr in its document (if it has one), it's a photo
                 # If it's a MessageMediaPhoto without a document, it's likely a GIF sent as photo
                 if hasattr(reply_msg.media, 'document') and reply_msg.media.document:
                     for attr in reply_msg.media.document.attributes:
                         if isinstance(attr, DocumentAttributeSticker):
                             media_type = "Animated Sticker (as Photo)"
                             break
                     else: # Only runs if loop didn't break (no sticker attr found)
                         # If it's a photo according to is_photo and has a document but no sticker attr,
                         # it's likely a static image sent as a document which is_photo caught, or a GIF sent as photo
                         # is_photo should catch GIFs sent as MessageMediaPhoto directly.
                         # Let's assume if it's a doc with no sticker attr, and is_photo is true, it's a photo doc
                         # Or if is_photo catches MessageMediaPhoto (which often are GIFs), it's a GIF
                         # The logic in is_photo is key here.
                         # For simplicity here, if is_photo is true and no sticker doc attr found, assume photo
                         # But if it's a MessageMediaPhoto, it's more likely a GIF if it has no doc.
                         # Let's refine based on is_photo's internal logic if needed.
                         # For now, if is_photo is True and no sticker doc attr, assume it's a photo (could be GIF as photo)
                         # is_photo likely returns True for MessageMediaPhoto (GIFs) and Documents with image attrs but no video/sticker.
                         # So, media_type = "Photo" is a good default if is_photo is True and no sticker.
                         # To distinguish GIFs sent as MessageMediaPhoto from static photos sent as MessageMediaPhoto is tricky without more checks.
                         # Let's stick with Photo for now if is_photo is True and no sticker attr.
                         media_type = "Photo"
                 else: # If it's just MessageMediaPhoto (not a document), likely a GIF sent as photo
                      # is_photo catches MessageMediaPhoto, which includes GIFs sent as photo.
                      # So, if is_photo is True, and it's not a document with sticker attr, it's either a static photo or a GIF as photo.
                      # Without more specific checks inside MessageMediaPhoto, we assume Photo.
                      # If we want to be more specific about GIFs as Photo, we'd need to check the photo's properties or attributes if any.
                      # For now, let's assume Photo for all is_photo True cases unless sticker doc attr found.
                      # This means GIFs sent as MessageMediaPhoto will be labeled as Photo.
                      # This is the current behavior of the is_photo helper function.
                      media_type = "Photo (GIF/Static)"
            elif hasattr(reply_msg.media, 'document') and reply_msg.media.document:
                is_video = False
                is_sticker = False
                is_audio = False
                is_voice = False
                is_round = False # Video note
                for attr in reply_msg.media.document.attributes:
                    if isinstance(attr, DocumentAttributeVideo):
                        is_video = True
                        if attr.round_message:
                            media_type = "Round Video (Video Note)"
                        elif attr.supports_streaming:
                            media_type = "Video (Streaming)"
                        else:
                            media_type = "Video"
                        break # Stop checking other attrs once video is found
                    elif isinstance(attr, DocumentAttributeSticker):
                        is_sticker = True
                        # Check if animated - Telethon usually distinguishes animated stickers differently
                        # via DocumentAttributeAnimated or specific sticker types, but often just DocumentAttributeSticker
                        # is used, and the file type (e.g., TGS, or specific PNG/Lottie) indicates animation.
                        # For basic check, if it's a sticker attr, call it static unless proven otherwise.
                        # Animated stickers often have specific attributes or are handled differently by Telethon internally.
                        # Let's assume static if only DocumentAttributeSticker is present.
                        # Telethon's is_video/is_audio checks are more reliable for these.
                        media_type = "Static Sticker"
                        break
                    elif isinstance(attr, DocumentAttributeAudio):
                        is_voice = attr.voice
                        is_round = attr.voice and attr.waveform is not None # Often voice notes have waveforms
                        if is_voice:
                            if is_round:
                                media_type = "Voice Note"
                            else:
                                media_type = "Audio File"
                        else:
                            media_type = "Music File"
                        break
                else: # Only runs if none of the specific attrs (Video, Sticker, Audio) matched
                    # If it has a document but no specific known attribute like Video/Audio/Sticker,
                    # check for Filename attribute to confirm it's a general file
                    has_filename = any(isinstance(attr, DocumentAttributeFilename) for attr in reply_msg.media.document.attributes)
                    if has_filename:
                        media_type = "File"
                    else:
                        # This case might be rare, perhaps a document without standard attributes
                        media_type = "Media (Document, No Standard Attr)"
            else:
                # Should not happen if reply_msg.media is True, but just in case
                media_type = "Media (Other)"
        else:
            media_type = "Text Only"
        info_lines.append(f"**Media Type:** `{media_type}`")
        
        info_lines.append(f"**Has Media:** `{'Yes' if reply_msg.media else 'No'}`")
        info_lines.append(f"**Has Text:** `{'Yes' if reply_msg.message else 'No'}`")

        # Add size if message has media
        if reply_msg.media:
            # Try to get size from document attribute
            size_str = "Unknown"
            if hasattr(reply_msg.media, 'document') and reply_msg.media.document:
                size_str = get_file_size(reply_msg.media.document.size)
            # For photos, size might not be directly available unless sent as document
            # We just add a placeholder if it's a photo and not a document
            elif hasattr(reply_msg.media, 'photo') and reply_msg.media.photo: # Check for photo attribute if MessageMediaPhoto isn't direct
                 # Attempt to get size from document attributes if photo was sent as doc
                 # This is a fallback check, usually photos as doc will have doc attr
                 # Otherwise, size remains "Unknown"
                 size_str = "Size not available (simple photo)"
            info_lines.append(f"**Media Size:** `{size_str}`")

        # Sender info
        try:
            sender = await reply_msg.get_sender()
            if sender:
                sender_id = sender.id
                info_lines.append(f"**Sender ID:** [{sender_id}](tg://user?id={sender_id})") # Clickable link
                sender_username = sender.username or 'N/A'
                # Use the username for the clickable link part, not the display name
                info_lines.append(f"**Sender Username:** @{sender_username}")
                # The display name itself is not made clickable, but shown as text
                display_name = get_display_name(sender)
                info_lines.append(f"**Sender Name:** `{display_name}`")
        except Exception as e:
            info_lines.append(f"**Sender Info Error:** `{repr(e)}`")

        # Chat info
        try:
            chat = await reply_msg.get_chat()
            if chat:
                chat_id = chat.id
                # Note: tg://resolve for chats/groups might not work directly without username
                # Removed clickable link attempt due to unreliability
                info_lines.append(f"**Chat ID:** `{chat_id}`")
                chat_title = get_display_name(chat)
                info_lines.append(f"**Chat Title:** `{chat_title}`")
        except Exception as e:
            info_lines.append(f"**Chat Info Error:** `{repr(e)}`")

        # Media info (includes size already if applicable)
        if reply_msg.media:
            media_info = await get_media_info(reply_msg.media)
            info_lines.append("**Media Details:**")
            # Format media info if needed, for now just append
            info_lines.append(f"```\n{media_info}\n```") # Use code block for better readability

        # Final text
        full_info = "\n".join(info_lines)
        await event.edit(f"--- **Message Info** ---\n{full_info}\n------------------", parse_mode='Markdown')
        logger.debug("Info command executed and message edited.")
        return # Exit after handling 'info'

def setup(client_instance):
    """Setup function called by the module loader."""
    # The event handler is already registered using the decorator @client.on
    # This function can be used for any additional setup if needed in the future.
    logger.info("Info handler module loaded.")
    pass

# Define HELP_TEXT for the help command
HELP_TEXT = "**دستورهای دیگر:**\n• `info`  نمایش اطلاعات پیام ریپلای شده\n\n"