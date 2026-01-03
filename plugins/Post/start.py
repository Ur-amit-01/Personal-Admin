from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter

# =====================================================================================

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)  # React with a random emoji
    except:
        pass

    # Add user to the database if they don't exist
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id)
        total_users = await db.total_users_count()
        await client.send_message(LOG_CHANNEL, LOG_TEXT.format(message.from_user.mention, message.from_user.id, total_users))

    # Welcome message
    txt = (
        f"> **✨👋🏻 Hey {message.from_user.mention} !!**\n\n"
        f"**Welcome to the Channel Manager Bot, Manage multiple channels and post messages with ease! 😌**\n\n"
    )
    button = InlineKeyboardMarkup([
        [InlineKeyboardButton('📜 ᴀʙᴏᴜᴛ', callback_data='about'), InlineKeyboardButton('🕵🏻‍♀️ ʜᴇʟᴘ', callback_data='help')]
    ])

    # Send the start message with or without a picture
    if START_PIC:
        await message.reply_photo(START_PIC, caption=txt, reply_markup=button)
    else:
        await message.reply_text(text=txt, reply_markup=button, disable_web_page_preview=True)


@Client.on_message(filters.command("id"))
async def id_command(client: Client, message: Message):
    if message.chat.title:
        chat_title = message.chat.title
    else:
        chat_title = message.from_user.full_name

    id_text = f"**Chat ID of** {chat_title} **is**\n`{message.chat.id}`"

    await client.send_message(
        chat_id=message.chat.id,
        text=id_text,
        reply_to_message_id=message.id,
    )
# =====================================================================================
# Set bot commands
@Client.on_message(filters.command("set") & admin_filter)
async def set_commands(client: Client, message: Message):
    await client.set_bot_commands([
        BotCommand("start", "🤖 ꜱᴛᴀʀᴛ ᴍᴇ"),
        BotCommand("channels", "📋 ʟɪꜱᴛ ᴏꜰ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴄʜᴀɴɴᴇʟꜱ"),
        BotCommand("admin", "🛠️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"),
        BotCommand("post", "📢 ꜱᴇɴᴅ ᴘᴏꜱᴛ"),
        BotCommand("fpost", "📢 sᴇɴᴅ ᴘᴏsᴛ ᴡɪᴛʜ ғᴏʀᴡᴀʀᴅ ᴛᴀɢ"),
        BotCommand("del_post", "🗑️ ᴅᴇʟᴇᴛᴇ ᴘᴏꜱᴛ"),
        BotCommand("add", "➕ ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("rem", "➖ ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ"),
    ])
    await message.reply_text("✅ Bot commands have been set.")

#=====================================================================================
@Client.on_message(filters.private & filters.command("format"))
async def format_html_command(client: Client, message: Message):
    """Format HTML text - Reply to message or provide HTML directly"""
    
    html_content = ""
    
    # Get HTML from reply or command arguments
    if message.reply_to_message:
        # Get text from replied message
        if message.reply_to_message.text:
            html_content = message.reply_to_message.text
        elif message.reply_to_message.caption:
            html_content = message.reply_to_message.caption
        else:
            await message.reply("❌ Replied message has no text or caption.")
            return
    else:
        # Get HTML from command arguments
        if len(message.command) < 2:
            # Show usage help
            usage = (
                "📝 **Usage:**\n"
                "• `/format <html text>`\n"
                "• Reply to a message with `/format`\n\n"
                "**Example:**\n"
                "`/format <b>bold</b> <i>italic</i>`"
            )
            await message.reply(usage, parse_mode="Markdown", disable_web_page_preview=True)
            return
        
        html_content = message.text.split(' ', 1)[1]
    
    # Validate content
    if not html_content.strip():
        await message.reply("⚠️ No text to format.")
        return
    
    # Send processing message
    processing_msg = await message.reply("🔄 Formatting...")
    
    try:
        # Send formatted HTML
        await message.reply(
            html_content,
            parse_mode="HTML",
            disable_web_page_preview=True,
            quote=True
        )
        
        # Delete processing message
        await processing_msg.delete()
        
    except Exception as e:
        # Clean up and show error
        await processing_msg.delete()
        
        error_msg = f"❌ **Error:** `{str(e)[:200]}`"
        await message.reply(error_msg, parse_mode="Markdown")
