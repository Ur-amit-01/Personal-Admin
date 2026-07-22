import re
import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import RPCError
from pyrogram.enums import ParseMode


# =====================================================================
# CONFIG
# =====================================================================
DEFAULT_THUMB_PATH = "default_thumbnail.jpg"     # bundled thumbnail on your server
NOTES_DOMAIN = "static.pw.live"
SESSION_TIMEOUT_SECONDS = 300                    # 5 min — auto-expire stale sessions
MAX_THUMB_SIZE_BYTES = 5 * 1024 * 1024           # 5 MB safety cap on uploaded thumbnails

TEAM_LEGEND = [
    "MR Sir",
    "Amit Mahajan Sir",
    "Mohit Dadheech Sir",
    "Pankaj Sir",
    "Rupesh Sir",
    "Samapti Mam",
]

TEAM_ALPHA = [
    "Saleem Sir",
    "Sudhanshu Sir",
    "Om Pandey Sir",
    "SKC Sir",
    "Vipin Sir",
    "Akansha Mam",
]


# =====================================================================
# 🎨 CAPTION FORMATTING — edit ONLY this section to change output style
# =====================================================================
def build_caption(title: str, teacher: str, youtube_link: str | None, notes_link: str | None) -> str:
    """
    Builds the final caption sent with the media.
    Change the layout/wording/emojis here — nothing else needs to change.
    """
    lines = [
        f"<b>{title}</b>",
        f"<b>━━━━━━━✦✗✦━━━━━━━━━</b>",
        f"<blockquote><b>• Teacher: {teacher} ✍🏻</b></blockquote>",
    ]

    if youtube_link:
        lines.append(f'<blockquote><b>• YT : <a href="{youtube_link}">Click Here 🔗</a></b></blockquote>')

    if notes_link:
        lines.append(f'<blockquote><b>• Notes : <a href="{notes_link}">Click Here 📃</a></b></blockquote>')

    lines.append("")
    lines.append("<b><blockquote>Watch Now ♥️</blockquote></b>")

    return "\n".join(lines)


# =====================================================================
# SESSION STORE
# =====================================================================
# ⚠️ In-memory only — resets on bot restart. Swap for SQLite/Redis for production persistence.
pending_sessions: dict[int, dict] = {}


def session_expired(session: dict) -> bool:
    return (time.time() - session.get("created_at", 0)) > SESSION_TIMEOUT_SECONDS


async def cleanup_loop():
    """Background task: purges expired sessions every 60s so memory doesn't grow forever."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        expired = [uid for uid, s in pending_sessions.items()
                   if now - s.get("created_at", 0) > SESSION_TIMEOUT_SECONDS]
        for uid in expired:
            pending_sessions.pop(uid, None)


# Call this once when your bot starts, e.g. inside your main() after Client starts:
#   asyncio.create_task(cleanup_loop())


# =====================================================================
# EXTRACTION HELPERS
# =====================================================================
def extract_youtube_link(text: str):
    if not text:
        return None

    md_match = re.search(
        r"\[([^\]]+)\]\((https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s)]+)\)",
        text, re.IGNORECASE,
    )
    if md_match:
        return md_match.group(2)

    html_match = re.search(
        r'<a\s+href=["\'](https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^"\']+)["\']',
        text, re.IGNORECASE,
    )
    if html_match:
        return html_match.group(1)

    raw_match = re.search(
        r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+",
        text, re.IGNORECASE,
    )
    return raw_match.group(0) if raw_match else None


def extract_notes_link(text: str):
    if not text:
        return None

    domain = re.escape(NOTES_DOMAIN)

    md_match = re.search(rf"\[([^\]]+)\]\((https?://{domain}/[^\s)]+)\)", text, re.IGNORECASE)
    if md_match:
        return md_match.group(2)

    html_match = re.search(rf'<a\s+href=["\'](https?://{domain}/[^"\']+)["\']', text, re.IGNORECASE)
    if html_match:
        return html_match.group(1)

    raw_match = re.search(rf"(?:https?://)?{domain}/\S+", text, re.IGNORECASE)
    return raw_match.group(0) if raw_match else None


def extract_title(caption: str):
    if not caption:
        return None

    # 1. Structured format: "➭ Title » <value>" / "Title: <value>" / "Title - <value>"
    structured_match = re.search(r"title\s*[»:\-]\s*(.+)", caption, re.IGNORECASE)
    if structured_match:
        title = structured_match.group(1).strip()
        title = re.split(r"\s*➭", title)[0].strip()
        if title:
            return title

    # 2. Fallback: strip links, skip known metadata lines, grab first clean line
    text_no_links = re.sub(r"https?://\S+", "", caption)
    text_no_links = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text_no_links)
    text_no_links = re.sub(r"<a\s+href=.*?</a>", "", text_no_links, flags=re.IGNORECASE | re.DOTALL)

    for line in text_no_links.splitlines():
        line = line.strip(" -•➭\t")
        if line and not re.match(r"^(index|batch|quality|downloaded by)\b", line, re.IGNORECASE):
            return line

    return None


# =====================================================================
# KEYBOARDS
# =====================================================================
def thumb_choice_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖼 Default Thumbnail", callback_data="thumb::default"),
            InlineKeyboardButton("📤 Upload Thumbnail", callback_data="thumb::upload"),
        ]
    ])


def teacher_keyboard():
    rows = []
    for legend_name, alpha_name in zip(TEAM_LEGEND, TEAM_ALPHA):
        rows.append([
            InlineKeyboardButton(legend_name, callback_data=f"teacher::{legend_name}"),
            InlineKeyboardButton(alpha_name, callback_data=f"teacher::{alpha_name}"),
        ])
    return InlineKeyboardMarkup(rows)


# =====================================================================
# STEP 1: Video/Document + Caption received
# =====================================================================
@Client.on_message(
    filters.private & (filters.video | filters.document) & filters.caption,
    group=-1,
)
async def media_with_caption(client, message):
    user_id = message.from_user.id
    caption = message.caption or ""

    title = extract_title(caption)
    youtube_link = extract_youtube_link(caption)
    notes_link = extract_notes_link(caption)

    pending_sessions[user_id] = {
        "created_at": time.time(),
        "media_type": "video" if message.video else "document",
        "file_id": message.video.file_id if message.video else message.document.file_id,
        "title": title,
        "youtube_link": youtube_link,
        "notes_link": notes_link,
        "thumb_file_id": None,
        "thumb_path": None,
        "awaiting_title": title is None,
        "awaiting_thumb_choice": False,
        "awaiting_thumb_upload": False,
    }

    if not title:
        await message.reply_text("**✏️ Couldn't find a title. Please send it now:**")
        return

    pending_sessions[user_id]["awaiting_thumb_choice"] = True
    await message.reply_text("**🖼 Choose a thumbnail option:**", reply_markup=thumb_choice_keyboard())


# =====================================================================
# STEP 2: User replies with missing title
# =====================================================================
@Client.on_message(
    filters.text
    & filters.private
    & filters.create(lambda _, __, m: pending_sessions.get(m.from_user.id, {}).get("awaiting_title", False)),
    group=-1,
)
async def receive_title(client, message):
    user_id = message.from_user.id
    session = pending_sessions.get(user_id)
    if not session:
        return

    if session_expired(session):
        pending_sessions.pop(user_id, None)
        await message.reply_text("⚠️ Session timed out. Please resend the file.")
        return

    title = message.text.strip()
    if not title:
        await message.reply_text("⚠️ Title can't be empty. Please send a valid title:")
        return

    session["title"] = title
    session["awaiting_title"] = False
    session["awaiting_thumb_choice"] = True

    await message.reply_text("**🖼 Choose a thumbnail option:**", reply_markup=thumb_choice_keyboard())


# =====================================================================
# STEP 3: Thumbnail choice buttons
# =====================================================================
@Client.on_callback_query(filters.regex(r"^thumb::"))
async def thumb_choice_selected(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = pending_sessions.get(user_id)

    if not session:
        await callback_query.answer("⚠️ Session expired. Please resend the file.", show_alert=True)
        return

    if session_expired(session):
        pending_sessions.pop(user_id, None)
        await callback_query.answer("⚠️ Session timed out. Please resend the file.", show_alert=True)
        try:
            await callback_query.message.delete()
        except RPCError:
            pass
        return

    choice = callback_query.data.split("::", 1)[1]

    if choice == "default":
        if not os.path.exists(DEFAULT_THUMB_PATH):
            await callback_query.answer("❌ Default thumbnail file missing on server!", show_alert=True)
            return

        session["thumb_file_id"] = None
        session["thumb_path"] = DEFAULT_THUMB_PATH
        session["awaiting_thumb_choice"] = False

        try:
            await callback_query.message.edit_text("**👨‍🏫 Select Teacher:**", reply_markup=teacher_keyboard())
        except RPCError:
            pass
        await callback_query.answer()

    elif choice == "upload":
        session["awaiting_thumb_choice"] = False
        session["awaiting_thumb_upload"] = True

        try:
            await callback_query.message.edit_text(
                "**📤 Send the thumbnail image now.**\n_(Send /skip to use default instead)_"
            )
        except RPCError:
            pass
        await callback_query.answer()

    else:
        await callback_query.answer("⚠️ Unknown option.", show_alert=True)


# =====================================================================
# STEP 4: Receive uploaded thumbnail (or /skip)
# =====================================================================
@Client.on_message(
    filters.private
    & (filters.photo | filters.command("skip"))
    & filters.create(lambda _, __, m: pending_sessions.get(m.from_user.id, {}).get("awaiting_thumb_upload", False)),
    group=-1,
)
async def receive_thumb_upload(client, message):
    user_id = message.from_user.id
    session = pending_sessions.get(user_id)
    if not session:
        return

    if session_expired(session):
        pending_sessions.pop(user_id, None)
        await message.reply_text("⚠️ Session timed out. Please resend the file.")
        return

    # /skip → fall back to default thumbnail
    if message.text and message.text.strip().lower() == "/skip":
        if not os.path.exists(DEFAULT_THUMB_PATH):
            await message.reply_text("❌ Default thumbnail missing on server. Please contact admin.")
            return
        session["thumb_file_id"] = None
        session["thumb_path"] = DEFAULT_THUMB_PATH
        session["awaiting_thumb_upload"] = False
        await message.reply_text("**👨‍🏫 Select Teacher:**", reply_markup=teacher_keyboard())
        return

    if not message.photo:
        await message.reply_text("⚠️ That doesn't look like an image. Please send a photo, or /skip.")
        return

    try:
        if message.photo.file_size and message.photo.file_size > MAX_THUMB_SIZE_BYTES:
            await message.reply_text("⚠️ Image too large (max 5MB). Please send a smaller one, or /skip.")
            return

        session["thumb_file_id"] = message.photo.file_id
        session["thumb_path"] = None
        session["awaiting_thumb_upload"] = False

        await message.reply_text("**👨‍🏫 Select Teacher:**", reply_markup=teacher_keyboard())

    except Exception:
        # Catch-all safety net — never let a bad upload crash the handler
        session["thumb_file_id"] = None
        session["thumb_path"] = DEFAULT_THUMB_PATH if os.path.exists(DEFAULT_THUMB_PATH) else None
        session["awaiting_thumb_upload"] = False

        if session["thumb_path"]:
            await message.reply_text(
                "❌ Failed to process thumbnail. Falling back to default.\n\n**👨‍🏫 Select Teacher:**",
                reply_markup=teacher_keyboard(),
            )
        else:
            await message.reply_text("❌ Failed to process thumbnail and no default available. Please resend the file.")
            pending_sessions.pop(user_id, None)


# =====================================================================
# FINAL SEND
# =====================================================================
async def send_final_media(client, chat_id, session, caption):
    thumb = session.get("thumb_file_id") or session.get("thumb_path")

    try:
        if session["media_type"] == "video":
            await client.send_video(chat_id, session["file_id"], caption=caption, thumb=thumb, parse_mode=ParseMode.HTML)
        else:
            await client.send_document(chat_id, session["file_id"], caption=caption, thumb=thumb, parse_mode=ParseMode.HTML)

    except RPCError as e:
        # Retry once without thumbnail in case the thumb itself caused the failure
        try:
            await client.send_message(chat_id, f"⚠️ Send with thumbnail failed ({e}). Retrying without thumbnail...")
            if session["media_type"] == "video":
                await client.send_video(chat_id, session["file_id"], caption=caption, parse_mode=ParseMode.HTML)
            else:
                await client.send_document(chat_id, session["file_id"], caption=caption, parse_mode=ParseMode.HTML)
        except RPCError as e2:
            await client.send_message(chat_id, f"❌ Failed to send media: {e2}")

    except Exception as e:
        # Absolute last-resort safety net so nothing here can ever crash the bot process
        try:
            await client.send_message(chat_id, f"❌ Unexpected error while sending media: {e}")
        except RPCError:
            pass


# =====================================================================
# STEP 5: Teacher selected -> build caption -> send
# =====================================================================
@Client.on_callback_query(filters.regex(r"^teacher::"))
async def teacher_selected(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = pending_sessions.get(user_id)

    if (not session
            or session.get("awaiting_title")
            or session.get("awaiting_thumb_choice")
            or session.get("awaiting_thumb_upload")):
        await callback_query.answer("⚠️ Session expired or incomplete. Please resend the file.", show_alert=True)
        return

    if session_expired(session):
        pending_sessions.pop(user_id, None)
        await callback_query.answer("⚠️ Session timed out. Please resend the file.", show_alert=True)
        return

    teacher = callback_query.data.split("::", 1)[1]
    caption = build_caption(session["title"], teacher, session["youtube_link"], session["notes_link"])

    await send_final_media(client, callback_query.message.chat.id, session, caption)

    try:
        await callback_query.message.delete()
    except RPCError:
        pass

    pending_sessions.pop(user_id, None)
    await callback_query.answer("✅ Sent!")
