import os
import ytthumb
import logging
from pyrogram import Client, filters
from pyrogram.types import (
    LinkPreviewOptions,
    Message
)
from config import *

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple help text
HELP_TEXT = "**Send YouTube video link with /t or /thumb command to get maximum quality thumbnail**\n\n**Example:** `/t https://youtu.be/xxxxx`"


@Client.on_message(filters.private & filters.command(["t", "thumb"]))
async def thumb_command(client: Client, message: Message):
    """Handle /t or /thumb command - get max quality thumbnail"""
    
    try:
        # Check if URL is provided
        if len(message.command) < 2:
            await message.reply_text(
                text=HELP_TEXT,
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            return
        
        # Get the URL from command
        url = message.command[1]
        logger.info(f"Thumbnail requested for URL: {url} by user: {message.from_user.id}")
        
        # Send processing message
        processing_msg = await message.reply_text(
            text="`🔍 Processing YouTube thumbnail...`",
            quote=True
        )
        
        try:
            # Get thumbnail with max quality
            logger.info("Attempting to fetch maxres thumbnail")
            thumbnail = ytthumb.thumbnail(video=url, quality="maxres")
            
            # If maxres fails, try hq as fallback
            if not thumbnail:
                logger.info("maxres failed, trying hq quality")
                thumbnail = ytthumb.thumbnail(video=url, quality="hq")
            
            if thumbnail:
                logger.info(f"Thumbnail fetched successfully: {thumbnail}")
                # Send thumbnail without caption
                await message.reply_photo(
                    photo=thumbnail,
                    quote=True
                )
                await processing_msg.delete()
            else:
                logger.error("No thumbnail returned from ytthumb")
                await processing_msg.edit_text(
                    text="❌ Could not fetch thumbnail. Please check the URL and try again.",
                    link_preview_options=LinkPreviewOptions(is_disabled=True)
                )
                
        except Exception as e:
            logger.error(f"Error in ytthumb: {str(e)}", exc_info=True)
            await processing_msg.edit_text(
                text=f"❌ Error: {str(e)}",
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            
    except Exception as e:
        logger.error(f"Unexpected error in thumb_command: {str(e)}", exc_info=True)
        try:
            await message.reply_text(
                text="❌ An unexpected error occurred. Please try again later.",
                link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except:
            pass
