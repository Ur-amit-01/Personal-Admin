from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
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
async def format_html_command(client, message: Message):
    """
    Convert HTML to Telegram formatted text
    Usage: /format <html> or reply to a message with /format
    """
    # Get the HTML text
    if message.reply_to_message:
        html_text = message.reply_to_message.text or message.reply_to_message.caption
    else:
        if len(message.command) > 1:
            html_text = ' '.join(message.command[1:])
        else:
            await message.reply_text(
                "**Usage:**\n"
                "• Reply to an HTML message with `/format`\n"
                "• Or send `/format <your_html_here>`\n\n"
                "**Example:**\n"
                '`/format <b>Hello</b> click <a href="https://example.com">here</a>`'
            )
            return
    
    if not html_text:
        await message.reply_text("❌ No text found to format.")
        return
    
    # Send with HTML parse mode - Telegram will format it automatically
    try:
        await message.reply_text(
            html_text,
            parse_mode="html",  # THIS IS THE MAGIC LINE
            disable_web_page_preview=True,
            reply_to_message_id=message.reply_to_message.id if message.reply_to_message else None
        )
    except Exception as e:
        # If Telegram can't parse the HTML, try to clean it first
        await message.reply_text(
            "❌ Telegram couldn't parse the HTML. Trying cleaned version...",
            reply_to_message_id=message.id
        )
        
        # Clean common HTML issues
        cleaned_html = clean_html_for_telegram(html_text)
        
        try:
            await message.reply_text(
                cleaned_html,
                parse_mode="html",
                disable_web_page_preview=True
            )
        except Exception as e2:
            await message.reply_text(
                f"❌ Failed to parse even after cleaning.\nError: `{str(e2)[:100]}`"
            )

def clean_html_for_telegram(html_text):
    """Clean HTML to make it compatible with Telegram's parser"""
    # Fix: ### href="url"sb>TEXT</b></a> -> <a href="url"><b>TEXT</b></a>
    html_text = re.sub(
        r'###\s*href="([^"]+)"[^>]*>sb>([^<]+)</b></a>',
        r'<a href="\1"><b>\2</b></a>',
        html_text
    )
    
    # Fix: href="url">sb>TEXT</b></a> -> <a href="url"><b>TEXT</b></a>
    html_text = re.sub(
        r'href="([^"]+)"[^>]*>sb>([^<]+)</b></a>',
        r'<a href="\1"><b>\2</b></a>',
        html_text
    )
    
    # Fix: ### </b><a href -> <a href
    html_text = re.sub(r'###\s*</b><a\s+', '<a ', html_text)
    
    # Remove empty bold tags
    html_text = re.sub(r'</b><b>', '', html_text)
    html_text = re.sub(r'<b>\s*</b>', '', html_text)
    
    # Fix unclosed tags
    html_text = html_text.replace('<sb>', '<b>')
    html_text = html_text.replace('</sb>', '</b>')
    
    # Ensure all <a> tags are properly closed
    html_text = re.sub(r'<a\s+href="([^"]+)"[^>]*>([^<]+)(?!</a>)', r'<a href="\1">\2</a>', html_text)
    
    return html_text
