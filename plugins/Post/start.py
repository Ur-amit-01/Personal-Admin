
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand, ForceReply
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
import html
import re
import datetime
from datetime import timedelta
import pytz

# Add this global dictionary to store user states
user_states = {}

# Hardcoded channel ID - CHANGE THIS TO YOUR CHANNEL ID
CHANNEL_ID = -1001234567890  # Replace with your channel ID

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc

# =====================================================================================
# SIMPLE EBBINGHAUS SCHEDULING
# =====================================================================================

@Client.on_message(filters.private & filters.command("schedule"))
async def start_scheduling(client, message: Message):
    """Start the simple Ebbinghaus scheduling"""
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    # Initialize user state
    user_id = message.from_user.id
    user_states[user_id] = {
        'step': 1,  # 1=waiting for post, 2=waiting for date
        'post_text': None
    }
    
    instructions = """
📘 **Ebbinghaus Review Scheduler**

I'll schedule your post for 7 spaced reviews at **9:00 AM**.

**Just send me the post you want to schedule:**

Example:
`
• Basics Math : Lec 01
• Mole Concept : Lec 01 
• Living World : Lec 01
`

I'll add R1, R2... R7 and schedule them at **9:00 AM**.
"""
    
    await message.reply_text(
        instructions,
        reply_markup=ForceReply(placeholder="Paste your post here...")
    )

@Client.on_message(filters.private & filters.reply)
async def process_schedule(client, message: Message):
    """Process the schedule inputs"""
    user_id = message.from_user.id
    
    # Check if user is in scheduling mode
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if state['step'] == 1:
        # Store the post text
        user_states[user_id]['post_text'] = message.text.strip()
        user_states[user_id]['step'] = 2
        
        today = datetime.datetime.now(IST).date()
        tomorrow = today + timedelta(days=1)
        
        await message.reply_text(
            f"✅ **Post saved!**\n\n"
            f"📅 **Now enter the start date (YYYY-MM-DD format):**\n"
            f"• Today : `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{tomorrow.strftime('%Y-%m-%d')}`\n\n"
            f"*All posts will be scheduled at 9:00 AM *\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="Enter start date (YYYY-MM-DD)...")
        )
        
    elif state['step'] == 2:
        # Process date and schedule
        await schedule_posts(client, message, user_id)

async def schedule_posts(client, message: Message, user_id: int):
    """Schedule the posts in IST timezone"""
    date_input = message.text.strip()
    
    try:
        # Get current time in IST
        now_ist = datetime.datetime.now(IST)
        today_ist = now_ist.date()
        
        # Parse input date
        input_date = datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        
        if input_date < today_ist:
            await message.reply_text(
                "❌ **Date cannot be in the past!**\n"
                f"Please enter today's date or a future date.\n"
                f"Today is: `{today_ist.strftime('%Y-%m-%d')}`"
            )
            return
        
        # Get the post text
        post_text = user_states[user_id]['post_text']
        
        # Ebbinghaus intervals (days)
        intervals = [1, 3, 7, 14, 30, 60, 90]
        review_names = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        
        # Create summary
        summary = f"✅ **7 Posts Scheduled in Channel (IST)!**\n\n"
        summary += f"**Start Date:** {input_date.strftime('%d %B %Y')}\n"
        summary += f"**Posting Time:** 9:00 AM IST\n\n"
        summary += "📋 **Schedule:**\n"
        
        # Schedule each post
        scheduled_count = 0
        
        for i, day in enumerate(intervals):
            review_date = input_date + timedelta(days=day)
            
            # Create datetime in IST at 9:00 AM
            ist_time = IST.localize(
                datetime.datetime.combine(review_date, datetime.time(9, 0, 0))
            )
            
            # Convert IST to UTC for Telegram
            utc_time = ist_time.astimezone(UTC)
            
            date_formatted = review_date.strftime("%d %B %Y (%A)")
            
            # Add R1, R2, etc. to the post
            review_post = f"🔄 **{review_names[i]} - Day {day}**\n📅 {date_formatted}\n⏰ 9:00 AM IST\n\n{post_text}"
            
            try:
                # Schedule the post in channel
                await client.send_message(
                    chat_id=CHANNEL_ID,
                    text=review_post,
                    schedule_date=utc_time
                )
                
                scheduled_count += 1
                
                # Show time in summary (IST format)
                time_str = ist_time.strftime('%I:%M %p')
                summary += f"• **{review_names[i]} (Day {day}):** {review_date.strftime('%d %B %Y')} at {time_str} IST\n"
                
            except Exception as e:
                error_msg = str(e)
                if "SCHEDULE_DATE_INVALID" in error_msg:
                    summary += f"• ❌ **{review_names[i]}:** Date too far in future\n"
                else:
                    summary += f"• ❌ **{review_names[i]}:** Failed - {error_msg[:50]}...\n"
        
        summary += f"\n✅ **{scheduled_count}/7 posts scheduled successfully**"
        summary += f"\n\n📢 **Channel ID:** `{CHANNEL_ID}`"
        summary += f"\n⏰ **All times are in IST (UTC+5:30)**"
        
        # Show current IST time
        current_ist = datetime.datetime.now(IST).strftime('%d %B %Y, %I:%M %p %Z')
        summary += f"\n\n🕐 **Current IST Time:** {current_ist}"
        
        # Clear user state
        del user_states[user_id]
        
        # Send summary
        await message.reply_text(summary)
        
    except ValueError:
        await message.reply_text(
            "❌ **Invalid date format!**\n"
            "Please use **YYYY-MM-DD** format.\n"
            f"*Example: {datetime.datetime.now(IST).date().strftime('%Y-%m-%d')}*"
        )
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")
        if user_id in user_states:
            del user_states[user_id]

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
