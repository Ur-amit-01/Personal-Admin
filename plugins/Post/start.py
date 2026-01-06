from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand, ForceReply, ChatPrivileges
from pyrogram.enums import ChatMemberStatus
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
import re
import datetime
from datetime import timedelta
import pytz
import asyncio

# Add this global dictionary to store user states
user_states = {}

# Hardcoded channel ID - CHANGE THIS TO YOUR CHANNEL ID
CHANNEL_ID = -1003608039429  # Replace with your channel ID

# Timezone setup
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc

# User session client (for scheduling)
user_client = None

# =====================================================================================
# HELPER FUNCTIONS FOR USER ACCOUNT
# =====================================================================================

async def start_user_client():
    """Initialize and start the user client"""
    global user_client
    try:
        user_client = Client(
            "scheduler_user",
            session_string=SESSION_STRING,  # From your config
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True
        )
        await user_client.start()
        print("✅ User client started successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to start user client: {e}")
        return False

async def ensure_user_in_channel():
    """Ensure user account is admin in the channel"""
    try:
        # Check if user is already in channel
        try:
            member = await user_client.get_chat_member(CHANNEL_ID, "me")
            
            # Check if already admin
            if member.status == ChatMemberStatus.ADMINISTRATOR:
                print("✅ User is already admin in channel")
                return True
            else:
                # User is member but not admin
                print("ℹ️ User is member but not admin")
                return False
                
        except Exception as e:
            print(f"ℹ️ User not in channel: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking user status: {e}")
        return False

async def add_user_to_channel():
    """Add user account to channel as admin"""
    try:
        # Create invite link using bot
        from pyrogram import Client as BotClient
        bot_client = BotClient("bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        invite_link = await bot_client.create_chat_invite_link(CHANNEL_ID)
        await bot_client.stop()
        
        # Join channel with user account
        await user_client.join_chat(invite_link.invite_link)
        await asyncio.sleep(2)
        
        # Promote to admin using bot
        bot_client = BotClient("bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        user_id = (await user_client.get_me()).id
        await bot_client.promote_chat_member(
            CHANNEL_ID,
            user_id,
            privileges=ChatPrivileges(
                can_post_messages=True,
                can_edit_messages=True,
                can_delete_messages=True,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=True,
                can_manage_video_chats=False
            )
        )
        
        await bot_client.stop()
        await asyncio.sleep(2)
        
        print("✅ User added and promoted to admin")
        return True
        
    except Exception as e:
        print(f"❌ Failed to add user to channel: {e}")
        return False

async def remove_user_from_channel():
    """Remove user account from channel"""
    try:
        await user_client.leave_chat(CHANNEL_ID)
        print("✅ User removed from channel")
        return True
    except Exception as e:
        print(f"❌ Failed to remove user from channel: {e}")
        return False

# =====================================================================================
# EBBINGHAUS SCHEDULING WITH USER ACCOUNT
# =====================================================================================

@Client.on_message(filters.private & filters.command("neet"))
async def start_scheduling(client, message: Message):
    """Start the simple Ebbinghaus scheduling"""
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    # Check if we can schedule media
    if message.reply_to_message and (message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.document):
        # Handle media scheduling
        user_id = message.from_user.id
        user_states[user_id] = {
            'step': 2,  # Skip to date step since we have media
            'post_text': None,
            'media': message.reply_to_message,
            'media_type': 'photo' if message.reply_to_message.photo else 'video' if message.reply_to_message.video else 'document'
        }
        
        today = datetime.datetime.now(IST).date()
        tomorrow = today + timedelta(days=1)
        
        await message.reply_text(
            f"✅ **Media saved!**\n\n"
            f"📅 **Now enter the start date (YYYY-MM-DD format):**\n"
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{tomorrow.strftime('%Y-%m-%d')}`\n\n"
            f"*All posts will be scheduled at 9:00 AM*\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="Enter start date (YYYY-MM-DD)...")
        )
    else:
        # Handle text scheduling
        user_id = message.from_user.id
        user_states[user_id] = {
            'step': 1,  # 1=waiting for post, 2=waiting for date
            'post_text': None,
            'media': None,
            'media_type': None
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

**OR** reply to a photo/video with /schedule to schedule media!
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
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{tomorrow.strftime('%Y-%m-%d')}`\n\n"
            f"*All posts will be scheduled at 9:00 AM*\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="Enter start date (YYYY-MM-DD)...")
        )
        
    elif state['step'] == 2:
        # Process date and schedule
        await schedule_posts(client, message, user_id)

async def schedule_posts(client, message: Message, user_id: int):
    """Schedule the posts in IST timezone using user account"""
    date_input = message.text.strip()
    
    try:
        # Parse input date
        input_date = datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        
        # Initialize user client
        if not user_client:
            success = await start_user_client()
            if not success:
                await message.reply_text("❌ **Failed to initialize scheduler. Please try again.**")
                return
        
        # Ensure user is in channel as admin
        is_in_channel = await ensure_user_in_channel()
        if not is_in_channel:
            await message.reply_text("⏳ **Adding scheduler to channel...**")
            success = await add_user_to_channel()
            if not success:
                await message.reply_text("❌ **Failed to add scheduler to channel. Please make sure bot is admin.**")
                return
        
        # Get state data
        state = user_states[user_id]
        post_text = state.get('post_text', '')
        media = state.get('media')
        media_type = state.get('media_type')
        
        # Ebbinghaus intervals (days)
        intervals = [1, 3, 7, 14, 30, 60, 90]
        review_names = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        
        # Create summary
        summary = f"✅ **7 Posts Scheduling Started!**\n\n"
        summary += f"**Start Date:** {input_date.strftime('%d %B %Y')}\n"
        summary += f"**Posting Time:** 9:00 AM IST\n\n"
        summary += "📋 **Progress:**\n"
        
        # Send initial status
        status_msg = await message.reply_text("⏳ **Starting to schedule posts...**")
        
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
            
            # Create caption
            caption = f"🔄 **{review_names[i]} - Day {day}**\n📅 {date_formatted}\n⏰ 9:00 AM IST"
            if post_text:
                caption += f"\n\n{post_text}"
            
            try:
                if media:
                    # Schedule media
                    if media_type == 'photo' and media.photo:
                        await user_client.send_photo(
                            chat_id=CHANNEL_ID,
                            photo=media.photo.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                    elif media_type == 'video' and media.video:
                        await user_client.send_video(
                            chat_id=CHANNEL_ID,
                            video=media.video.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                    elif media_type == 'document' and media.document:
                        await user_client.send_document(
                            chat_id=CHANNEL_ID,
                            document=media.document.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                else:
                    # Schedule text
                    await user_client.send_message(
                        chat_id=CHANNEL_ID,
                        text=caption,
                        schedule_date=utc_time
                    )
                
                scheduled_count += 1
                
                # Update progress
                progress_msg = f"✅ **{review_names[i]}** scheduled for {review_date.strftime('%d %B %Y')}"
                await status_msg.edit_text(f"⏳ **Progress:** {i+1}/7 done\n{progress_msg}")
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                error_msg = str(e)
                if "SCHEDULE_DATE_INVALID" in error_msg:
                    summary += f"• ❌ **{review_names[i]}:** Date too far in future\n"
                else:
                    summary += f"• ❌ **{review_names[i]}:** Failed - {error_msg[:50]}...\n"
                
                await asyncio.sleep(2)  # Longer delay on error
        
        # Final summary
        summary = f"✅ **{scheduled_count}/7 Posts Scheduled Successfully!**\n\n"
        summary += f"**Start Date:** {input_date.strftime('%d %B %Y')}\n"
        summary += f"**Posting Time:** 9:00 AM IST\n\n"
        
        for i, day in enumerate(intervals):
            review_date = input_date + timedelta(days=day)
            summary += f"• **{review_names[i]} (Day {day}):** {review_date.strftime('%d %B %Y')}\n"
        
        summary += f"\n📢 **Channel ID:** `{CHANNEL_ID}`"
        summary += f"\n⏰ **All times are in IST (UTC+5:30)**"
        
        # Show current IST time
        current_ist = datetime.datetime.now(IST).strftime('%d %B %Y, %I:%M %p %Z')
        summary += f"\n\n🕐 **Current IST Time:** {current_ist}"
        
        # Remove user from channel after scheduling
        await message.reply_text("⏳ **Cleaning up scheduler...**")
        await remove_user_from_channel()
        
        # Clear user state
        del user_states[user_id]
        
        # Send final summary
        await status_msg.delete()
        await message.reply_text(summary)
        
    except ValueError:
        await message.reply_text(
            "❌ **Invalid date format!**\n"
            "Please use **YYYY-MM-DD** format.\n"
            f"*Example: {datetime.datetime.now(IST).date().strftime('%Y-%m-%d')}*"
        )
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)}")
        # Clean up on error
        try:
            await remove_user_from_channel()
        except:
            pass
        if user_id in user_states:
            del user_states[user_id]

# =====================================================================================
# REST OF YOUR EXISTING CODE (unchanged)
# =====================================================================================

@Client.on_message(filters.private & filters.command("start"))
async def start(client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass

    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id)
        total_users = await db.total_users_count()
        await client.send_message(LOG_CHANNEL, LOG_TEXT.format(message.from_user.mention, message.from_user.id, total_users))

    txt = (
        f"> **✨👋🏻 Hey {message.from_user.mention} !!**\n\n"
        f"**Welcome to the Channel Manager Bot!**\n\n"
        f"**New Feature:** Use `/schedule` to automatically schedule 7 Ebbinghaus reviews!\n"
        f"*Works with text AND media!*"
    )
    button = InlineKeyboardMarkup([
        [InlineKeyboardButton('📜 ᴀʙᴏᴜᴛ', callback_data='about'), InlineKeyboardButton('🕵🏻‍♀️ ʜᴇʟᴘ', callback_data='help')]
    ])

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

@Client.on_message(filters.command("set") & admin_filter)
async def set_commands(client: Client, message: Message):
    await client.set_bot_commands([
        BotCommand("start", "🤖 ꜱᴛᴀʀᴛ ᴍᴇ"),
        BotCommand("neet", "📅 ꜱᴄʜᴇᴅᴜʟᴇ ᴇʙʙɪɴɢʜᴀᴜꜱ ʀᴇᴠɪᴇᴡꜱ"),
        BotCommand("format", "📅 HTML to Markdown"),
        BotCommand("channels", "📋 ʟɪꜱᴛ ᴏꜰ ᴄᴏɴɴᴇᴄᴛᴇᴅ ᴄʜᴀɴɴᴇʟꜱ"),
        BotCommand("admin", "🛠️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ"),
        BotCommand("post", "📢 ꜱᴇɴᴅ ᴘᴏꜱᴛ"),
        BotCommand("fpost", "📢 sᴇɴᴅ ᴘᴏsᴛ ᴡɪᴛʜ ғᴏʀᴡᴀʀᴅ ᴛᴀɢ"),
        BotCommand("del_post", "🗑️ ᴅᴇʟᴇᴛᴇ ᴘᴏꜱᴛ"),
        BotCommand("add", "➕ ᴀᴅᴅ ᴄʜᴀɴɴᴇʟ"),
        BotCommand("rem", "➖ ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ"),
    ])
    await message.reply_text("✅ Bot commands have been set.")

@Client.on_message(filters.private & filters.command("format"))
async def format_command(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("❗ Please reply to a message using /format")
        return

    replied = message.reply_to_message

    if replied.text:
        await message.reply(replied.text)
    elif replied.caption:
        await message.reply(replied.caption)
    else:
        await message.reply("❗ Replied message has no text to send")

# =====================================================================================
# START USER CLIENT WHEN BOT STARTS
# =====================================================================================

#async def initialize():
    #"""Initialize user client on startup"""
    #await start_user_client()
    #print("🚀 Scheduler ready!")

# Run initialization when bot starts
#import threading
#def run_async_init():
    #loop = asyncio.new_event_loop()
    #asyncio.set_event_loop(loop)
    #loop.run_until_complete(initialize())

#thread = threading.Thread(target=run_async_init, daemon=True)
#thread.start()
