import time
import platform
import random

from pyrogram import Client, filters, __version__ as pyrogram_version
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,
)

# =====================================================================================
# Fully self-contained module — no imports from config/, plugins/, or any other
# local package. Everything this file needs is defined right here.
# =====================================================================================

BOT_START_TIME = time.time()          # used for uptime stats
START_PIC = None                       # set to an image url/file_id to send a photo instead of text
REACTIONS = ["🎉", "🔥", "❤️", "😎", "🤖", "✨"]

# In-memory user tracking (no external db). Resets on restart — swap in a real
# db later if persistence across restarts is needed.
SEEN_USERS = set()


def get_uptime() -> str:
    seconds = int(time.time() - BOT_START_TIME)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📜 ᴀʙᴏᴜᴛ", callback_data="about"),
                InlineKeyboardButton("🕵🏻‍♀️ ʜᴇʟᴘ", callback_data="help"),
            ],
            [InlineKeyboardButton("📊 sᴛᴀᴛs", callback_data="stats")],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="start_back")]]
    )


# =====================================================================================
# /start command
# =====================================================================================

@Client.on_message(filters.private & filters.command("start"))
async def start(client: Client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except Exception:
        pass

    SEEN_USERS.add(message.from_user.id)

    txt = (
        f"> **✨👋🏻 Hey {message.from_user.mention} !!**\n\n"
        f"**Welcome! I'm up and running — tap a button below to explore. 😌**\n\n"
        f"⏱ **Uptime:** `{get_uptime()}`"
    )

    if START_PIC:
        await message.reply_photo(START_PIC, caption=txt, reply_markup=main_menu())
    else:
        await message.reply_text(
            text=txt, reply_markup=main_menu(), disable_web_page_preview=True
        )


# =====================================================================================
# Callback navigation: about / help / stats / back
# =====================================================================================

@Client.on_callback_query(filters.regex("^about$"))
async def cb_about(client: Client, query: CallbackQuery):
    txt = (
        "**📜 ᴀʙᴏᴜᴛ**\n\n"
        "• **Language:** Python\n"
        f"• **Framework:** Pyrogram v{pyrogram_version}\n"
        f"• **Python:** {platform.python_version()}\n"
        f"• **Uptime:** `{get_uptime()}`"
    )
    await query.message.edit_text(txt, reply_markup=back_menu())
    await query.answer()


@Client.on_callback_query(filters.regex("^help$"))
async def cb_help(client: Client, query: CallbackQuery):
    txt = (
        "**🕵🏻‍♀️ ʜᴇʟᴘ**\n\n"
        "**/start** — show the welcome menu\n"
        "**/id** — get the current chat's ID\n"
        "**/stats** — bot uptime & usage stats"
    )
    await query.message.edit_text(txt, reply_markup=back_menu())
    await query.answer()


@Client.on_callback_query(filters.regex("^stats$"))
async def cb_stats(client: Client, query: CallbackQuery):
    txt = (
        "**📊 sᴛᴀᴛs**\n\n"
        f"⏱ **Uptime:** `{get_uptime()}`\n"
        f"👥 **Users seen this session:** `{len(SEEN_USERS)}`"
    )
    await query.message.edit_text(txt, reply_markup=back_menu())
    await query.answer()


@Client.on_callback_query(filters.regex("^start_back$"))
async def cb_back(client: Client, query: CallbackQuery):
    txt = (
        f"> **✨👋🏻 Hey {query.from_user.mention} !!**\n\n"
        f"**Welcome! I'm up and running — tap a button below to explore. 😌**\n\n"
        f"⏱ **Uptime:** `{get_uptime()}`"
    )
    await query.message.edit_text(
        txt, reply_markup=main_menu(), disable_web_page_preview=True
    )
    await query.answer()


# =====================================================================================
# /id command — standalone, no admin/db dependency
# =====================================================================================

@Client.on_message(filters.command("id"))
async def id_command(client: Client, message: Message):
    chat_title = message.chat.title if message.chat.title else message.from_user.full_name
    id_text = f"**Chat ID of** {chat_title} **is**\n`{message.chat.id}`"
    await client.send_message(
        chat_id=message.chat.id,
        text=id_text,
        reply_to_message_id=message.id,
    )


# =====================================================================================
# /stats command — plain text version (in case someone doesn't want to tap buttons)
# =====================================================================================

@Client.on_message(filters.command("stats"))
async def stats_command(client: Client, message: Message):
    txt = (
        "**📊 sᴛᴀᴛs**\n\n"
        f"⏱ **Uptime:** `{get_uptime()}`\n"
        f"👥 **Users seen this session:** `{len(SEEN_USERS)}`"
    )
    await message.reply_text(txt)
  
