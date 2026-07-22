import re
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# ---------------- CONFIG ----------------
TEACHERS = [
    # Team Legend
    "MR Sir",
    "Amit Mahajan Sir",
    "Mohit Dadheech Sir",
    "Pankaj Sir",
    "Rupesh Sir",
    "Samapti Mam",

    # Team Alpha
    "Saleem Sir",
    "Sudhanshu Sir",
    "Om Pandey Sir",
    "SKC Sir",
    "Vipin Sir",
    "Akansha Mam",
]
NOTES_DOMAIN = "static.pw.live"

# in-memory session store: { user_id: {...pending data...} }
# ⚠️ resets on bot restart — swap for a DB (SQLite/Redis) in production
pending_sessions = {}

# ---------------- HELPERS ----------------
def extract_youtube_link(text: str):
    pattern = r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/\S+"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None

def extract_notes_link(text: str):
    pattern = rf"(?:https?://)?{re.escape(NOTES_DOMAIN)}/\S+"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(0) if match else None

def extract_title(caption: str):
    if not caption:
        return None
    text_no_links = re.sub(r"https?://\S+", "", caption)
    for line in text_no_links.splitlines():
        line = line.strip(" -•\t")
        if line:
            return line
    return None

def build_caption(title, teacher, youtube_link, notes_link):
    lines = [f"<b>{title}</b>", "", f"<b>👨‍🏫 Teacher:</b> {teacher}"]
    if youtube_link:
        lines.append(f"<b>▶️ Video:</b> {youtube_link}")
    if notes_link:
        lines.append(f"<b>📄 Notes:</b> {notes_link}")
    return "\n".join(lines)

def teacher_keyboard():
    buttons = [[InlineKeyboardButton(t, callback_data=f"teacher::{t}")] for t in TEACHERS]
    return InlineKeyboardMarkup(buttons)


# ---------------- STEP 1: Video/File + Caption received ----------------
@Client.on_message(
    filters.private
    & (filters.video | filters.document)
    & filters.caption,
    group=-1,  # run before other text/caption handlers
)
async def media_with_caption(client, message):
    caption = message.caption or ""
    title = extract_title(caption)
    youtube_link = extract_youtube_link(caption)
    notes_link = extract_notes_link(caption)

    pending_sessions[message.from_user.id] = {
        "media_type": "video" if message.video else "document",
        "file_id": message.video.file_id if message.video else message.document.file_id,
        "title": title,
        "youtube_link": youtube_link,
        "notes_link": notes_link,
        "awaiting_title": title is None,
    }

    if not title:
        await message.reply_text("**✏️ Couldn't find a title. Please send it now:**")
        return

    await message.reply_text("**👨‍🏫 Select Teacher:**", reply_markup=teacher_keyboard())


# ---------------- STEP 2: User replies with missing title ----------------
@Client.on_message(
    filters.text
    & filters.private
    & filters.create(lambda _, __, m: pending_sessions.get(m.from_user.id, {}).get("awaiting_title", False)),
    group=-1,  # intercept before other text handlers (e.g. auto_thumbnail)
)
async def receive_title(client, message):
    session = pending_sessions.get(message.from_user.id)
    if not session:
        return

    session["title"] = message.text.strip()
    session["awaiting_title"] = False

    await message.reply_text("**👨‍🏫 Select Teacher:**", reply_markup=teacher_keyboard())


# ---------------- STEP 3: Teacher selected -> send final media ----------------
@Client.on_callback_query(filters.regex(r"^teacher::"))
async def teacher_selected(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    session = pending_sessions.get(user_id)

    if not session or session.get("awaiting_title"):
        await callback_query.answer("⚠️ Session expired. Please resend the file.", show_alert=True)
        return

    teacher = callback_query.data.split("::", 1)[1]
    caption = build_caption(session["title"], teacher, session["youtube_link"], session["notes_link"])

    if session["media_type"] == "video":
        await client.send_video(callback_query.message.chat.id, session["file_id"], caption=caption)
    else:
        await client.send_document(callback_query.message.chat.id, session["file_id"], caption=caption)

    await callback_query.message.delete()
    pending_sessions.pop(user_id, None)
    await callback_query.answer("✅ Sent!")
