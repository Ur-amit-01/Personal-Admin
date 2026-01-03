from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
import html
import re

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




def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return html.escape(text)

def telegram_to_html(text: str, message: Message = None) -> str:
    """Convert Telegram formatting to HTML"""
    if not text:
        return ""
    
    # Escape HTML first
    text = escape_html(text)
    
    # Replace Telegram formatting with HTML tags
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
    
    # Italic
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
    
    # Underline
    text = re.sub(r'--(.*?)--', r'<u>\1</u>', text)
    
    # Strikethrough
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)
    
    # Code
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # Preformatted (multiline code)
    text = re.sub(r'```(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    
    # Spoiler
    text = re.sub(r'\|\|(.*?)\|\|', r'<span class="tg-spoiler">\1</span>', text)
    
    # Links (if not already in message entities)
    # This is a simple regex for URLs, for better parsing use message.entities
    text = re.sub(
        r'(https?://[^\s]+)',
        r'<a href="\1">\1</a>',
        text
    )
    
    # Line breaks
    text = text.replace('\n', '<br>')
    
    return text

@Client.on_message(filters.command("html"))
async def html_command(client: Client, message: Message):
    """Convert text to HTML"""
    
    if message.reply_to_message:
        # Get text from replied message
        source_msg = message.reply_to_message
        
        # Extract text based on message type
        if source_msg.text:
            text = source_msg.text
        elif source_msg.caption:
            text = source_msg.caption
        else:
            await message.reply("❌ The replied message has no text to convert.")
            return
        
        # Convert to HTML
        html_text = telegram_to_html(text, source_msg)
        
        # Create response
        response = (
            f"**📝 HTML Conversion**\n\n"
            f"**Original:**\n{text[:200]}...\n\n" if len(text) > 200 else f"**Original:**\n{text}\n\n"
            f"**HTML:**\n```html\n{html_text}\n```\n\n"
            f"**Preview:**\n{html_text}"
        )
        
    elif len(message.command) > 1:
        # Get text from command arguments
        text = " ".join(message.command[1:])
        html_text = telegram_to_html(text)
        
        response = (
            f"**📝 HTML Conversion**\n\n"
            f"**Original:**\n{text}\n\n"
            f"**HTML:**\n```html\n{html_text}\n```\n\n"
            f"**Preview:**\n{html_text}"
        )
        
    else:
        response = (
            "**ℹ️ Usage:**\n"
            "• Reply to a message: `/html`\n"
            "• With text: `/html your *text* here`\n\n"
            "**Supported formatting:**\n"
            "• **Bold**: `**text**` or `__text__`\n"
            "• *Italic*: `*text*` or `_text_`\n"
            "• ~~Strikethrough~~: `~~text~~`\n"
            "• `Code`: `text`\n"
            "• ```\nPreformatted\n```: ` ```text``` `\n"
            "• ||Spoiler||: `||text||`\n"
            "• [Links](https://t.me): `https://...`"
        )
    
    await message.reply(response, disable_web_page_preview=True)
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

#====================================================================================
@Client.on_message(filters.private & filters.command("format"))
async def format_command(client: Client, message: Message):
    # Check if /format is a reply to another message
    if not message.reply_to_message:
        await message.reply("❗ Please reply to a message using /format")
        return

    replied = message.reply_to_message

    # If replied message has text
    if replied.text:
        await message.reply(replied.text)

    # If replied message has caption (photo, video, doc, etc.)
    elif replied.caption:
        await message.reply(replied.caption)

    else:
        await message.reply("❗ Replied message has no text to send")
