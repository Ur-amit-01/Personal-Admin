from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
import time
import asyncio  # ADD THIS IMPORT

# =====================================================================================

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass

    # Add user to the database if they don't exist
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id)
        total_users = await db.total_users_count()
        await client.send_message(LOG_CHANNEL, LOG_TEXT.format(message.from_user.mention, message.from_user.id, total_users))

    # Advanced animated welcome message
    txt = f"""
╔═══════════════════════╗
       🚀 **WELCOME** 🚀
╚═══════════════════════╝

✨ **Hello {message.from_user.mention}!** ✨

━━━━━━━━━━━━━━━━━━━━━━
📊 **Your Stats:**
   ├─ 🆔 **User ID:** `{message.from_user.id}`
   ├─ 📅 **Joined:** {time.strftime('%Y-%m-%d %H:%M:%S')}
   └─ 👤 **Username:** @{message.from_user.username if message.from_user.username else "Not Set"}

━━━━━━━━━━━━━━━━━━━━━━
🤖 **About This Bot:**
   ├─ 📢 **Multi-Channel Manager**
   ├─ 🚀 **Auto Posting System**
   ├─ ⏰ **Scheduled Deletion**
   ├─ 🔧 **Group Management**
   ├─ 📊 **Analytics & Logs**
   └─ 🔒 **Admin Controls**

━━━━━━━━━━━━━━━━━━━━━━
💡 **Quick Start:**
   1️⃣ Add channels with `/add`
   2️⃣ Post with `/post` or `/fpost`
   3️⃣ Manage with `/admin`

━━━━━━━━━━━━━━━━━━━━━━
⭐ **Features:**
   ✅ **Bulk Posting** - Post to multiple channels
   ✅ **Auto Delete** - Schedule message removal
   ✅ **Channel Groups** - Organize channels
   ✅ **Forward Tag** - Preserve forward info
   ✅ **Error Handling** - Smart failure management
   ✅ **Log System** - Track all activities

━━━━━━━━━━━━━━━━━━━━━━
📞 **Support & Updates:**
   └─ 👨‍💻 **Developer:** [xDzoddd](https://t.me/xdzoddd)

╔═══════════════════════╗
   **Ready to Manage!** 🎯
╚═══════════════════════╝
"""

    # Stylish buttons with emojis
    button = InlineKeyboardMarkup([
        [
            InlineKeyboardButton('📖 About', callback_data='about'),
            InlineKeyboardButton('❓ Help', callback_data='help')
        ],
        [
            InlineKeyboardButton('➕ Add Channel', callback_data='channel_help'),
            InlineKeyboardButton('📢 Post Guide', callback_data='post_help')
        ],
        [
            InlineKeyboardButton('🛠️ Admin Panel', callback_data='admin'),
            InlineKeyboardButton('📊 Statistics', callback_data='stats')
        ],
        [
            InlineKeyboardButton('🔗 Contact Dev', url='https://t.me/xdzoddd'),
            InlineKeyboardButton('⭐ Rate Bot', url='https://t.me/botfather')
        ]
    ])

    # Send animated message (if START_PIC exists) or text
    if START_PIC:
        # You can add caption formatting for photos too
        caption = f"""
✨ **Welcome {message.from_user.mention}!** ✨

🚀 **Channel Manager Bot**
Manage multiple channels with ease!

📌 **Quick Commands:**
• `/add` - Add channel
• `/post` - Send post
• `/admin` - Admin panel
• `/help` - Get help

👉 **Click buttons below for more!**
        """
        await message.reply_photo(
            START_PIC, 
            caption=caption, 
            reply_markup=button,
            parse_mode="markdown"
        )
    else:
        # Send the styled text message
        await message.reply_text(
            text=txt, 
            reply_markup=button, 
            disable_web_page_preview=True,
            parse_mode="markdown"
        )
    
    # Optional: Send a follow-up animated message
    # Uncomment this if you want the follow-up message
    # await asyncio.sleep(1)
    # welcome_followup = """
    # 🎉 **Getting Started Guide** 🎉
    # 
    # Here's how to begin:
    # ━━━━━━━━━━━━━━━━━━━━━━
    # 1️⃣ **ADD CHANNELS**
    #    Use `/add <channel_id>` to connect channels
    # 
    # 2️⃣ **ORGANIZE GROUPS**
    #    Channels are organized in groups (0-3)
    # 
    # 3️⃣ **POST MESSAGES**
    #    Use `/post` or `/fpost` to broadcast
    # 
    # 4️⃣ **MANAGE**
    #    Use `/admin` for advanced controls
    # 
    # 💡 **Tip:** Reply to any message with `/post` to send it!
    # """
    # 
    # await message.reply_text(welcome_followup, disable_web_page_preview=True, parse_mode="markdown")

# =====================================================================================

@Client.on_message(filters.command("id"))
async def id_command(client: Client, message: Message):
    if message.chat.title:
        chat_title = message.chat.title
    else:
        chat_title = message.from_user.full_name

    # Stylish ID display
    id_text = f"""
🔍 **Chat Information** 🔍

━━━━━━━━━━━━━━━━━━━━━━
📛 **Name:** {chat_title}
🆔 **ID:** `{message.chat.id}`
👥 **Type:** {'Group' if message.chat.type in ['group', 'supergroup'] else 'Private Chat'}

━━━━━━━━━━━━━━━━━━━━━━
💡 **Usage:**
   • Copy this ID to add channels
   • Use in `/add` command
   • Share carefully!

━━━━━━━━━━━━━━━━━━━━━━
⚡ **Quick Copy:** `{message.chat.id}`
"""

    await client.send_message(
        chat_id=message.chat.id,
        text=id_text,
        reply_to_message_id=message.id,
        parse_mode="markdown"
    )

# =====================================================================================
# Set bot commands
@Client.on_message(filters.command("set") & admin_filter)
async def set_commands(client: Client, message: Message):
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("channels", "📋 List connected channels"),
        BotCommand("admin", "🛠️ Admin panel"),
        BotCommand("post", "📢 Send post to channels"),
        BotCommand("fpost", "📨 Send post with forward tag"),
        BotCommand("del_post", "🗑️ Delete existing post"),
        BotCommand("add", "➕ Add new channel"),
        BotCommand("rem", "➖ Remove channel"),
        BotCommand("id", "🆔 Get chat ID"),
        BotCommand("help", "❓ Get help & guide"),
    ]
    
    await client.set_bot_commands(commands)
    
    confirmation_msg = """
✅ **Bot Commands Updated!** ✅

━━━━━━━━━━━━━━━━━━━━━━
📋 **Available Commands:**
   ├─ 🚀 `/start` - Start the bot
   ├─ 📋 `/channels` - List channels
   ├─ 🛠️ `/admin` - Admin panel
   ├─ 📢 `/post` - Send posts
   ├─ 📨 `/fpost` - Forward posts
   ├─ 🗑️ `/del_post` - Delete posts
   ├─ ➕ `/add` - Add channel
   ├─ ➖ `/rem` - Remove channel
   ├─ 🆔 `/id` - Get chat ID
   └─ ❓ `/help` - Get help

━━━━━━━━━━━━━━━━━━━━━━
💡 **Commands are now visible in menu!**
"""
    
    await message.reply_text(confirmation_msg, parse_mode="markdown")
