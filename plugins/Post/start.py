from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand, ForceReply, ChatPrivileges
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, UserAlreadyParticipant
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
import re
import datetime
from datetime import timedelta
import pytz
import asyncio
import time

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
# HELPER FUNCTIONS FOR USER ACCOUNT - WITH PROPER ERROR HANDLING
# =====================================================================================

async def start_user_client():
    """Initialize and start the user client using your session string"""
    global user_client
    try:
        user_client = Client(
            "scheduler_user",
            session_string=SESSION_STRING,  # From your config
            api_id=API_ID,
            api_hash=API_HASH,
            sleep_threshold=60,
            in_memory=True
        )
        await user_client.start()
        user_id = (await user_client.get_me()).id
        print(f"✅ User client started successfully (ID: {user_id})")
        return True, user_id
    except Exception as e:
        print(f"❌ Failed to start user client: {e}")
        return False, None

async def check_bot_permissions():
    """Check if bot has necessary permissions"""
    try:
        bot_client = Client("bot_temp", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        try:
            bot_member = await bot_client.get_chat_member(CHANNEL_ID, "me")
            await bot_client.stop()
            
            if not hasattr(bot_member, 'privileges') or bot_member.privileges is None:
                return False, "❌ Bot is not an administrator in the channel"
            
            if not (bot_member.privileges.can_invite_users and bot_member.privileges.can_promote_members):
                return False, "❌ Bot needs both 'Invite Users' and 'Add Admins' permissions"
            
            return True, "✅ Bot has required permissions"
            
        except Exception as e:
            await bot_client.stop()
            return False, f"❌ Cannot access channel: {str(e)}"
            
    except Exception as e:
        return False, f"❌ Bot client error: {str(e)}"

async def ensure_user_in_channel():
    """Check if user is already in channel and get status"""
    try:
        member = await user_client.get_chat_member(CHANNEL_ID, "me")
        return True, member.status
    except Exception as e:
        print(f"User not in channel: {e}")
        return False, None

async def setup_assistant_in_channel(status_msg=None):
    """Set up assistant in channel - main function with proper error handling"""
    try:
        # Get user ID
        user_id = (await user_client.get_me()).id
        
        # Step 1: Check if already admin
        if status_msg:
            await status_msg.edit_text("🔍 **Checking assistant status...**")
        
        in_channel, current_status = await ensure_user_in_channel()
        
        if in_channel and current_status == ChatMemberStatus.ADMINISTRATOR:
            return True, "✅ Assistant is already admin in channel"
        
        # Step 2: Check bot permissions
        if status_msg:
            await status_msg.edit_text("🔍 **Checking bot permissions...**")
        
        perm_success, perm_msg = await check_bot_permissions()
        if not perm_success:
            return False, perm_msg
        
        # Step 3: Start bot client for operations
        bot_client = Client("bot_temp", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        try:
            # If user is member but not admin, promote them
            if in_channel and current_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED]:
                if status_msg:
                    await status_msg.edit_text("👑 **Promoting assistant to admin...**")
                
                try:
                    await bot_client.promote_chat_member(
                        CHANNEL_ID, 
                        user_id,
                        privileges=ChatPrivileges(
                            can_invite_users=True,
                            can_manage_chat=True,
                            can_delete_messages=True,
                            can_post_messages=True,
                            can_edit_messages=True,
                            can_pin_messages=True,
                            can_restrict_members=False,
                            can_promote_members=False,
                            can_manage_video_chats=False
                        )
                    )
                    await asyncio.sleep(2)
                    
                    # Verify promotion
                    assistant_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
                    if assistant_member.status != ChatMemberStatus.ADMINISTRATOR:
                        await bot_client.stop()
                        return False, "❌ Promotion verification failed"
                    
                    await bot_client.stop()
                    return True, "✅ Assistant promoted to admin"
                    
                except Exception as e:
                    await bot_client.stop()
                    return False, f"❌ Promotion failed: {str(e)}"
            
            # User not in channel at all
            else:
                if status_msg:
                    await status_msg.edit_text("🔗 **Creating invite link...**")
                
                # Create invite link
                try:
                    invite = await bot_client.create_chat_invite_link(CHANNEL_ID)
                    invite_url = invite.invite_link
                except Exception as e:
                    await bot_client.stop()
                    return False, f"❌ Cannot create invite link: {str(e)}"
                
                # Join channel
                if status_msg:
                    await status_msg.edit_text("🚪 **Joining channel...**")
                
                max_retries = 3
                last_error = None
                
                for attempt in range(max_retries):
                    try:
                        await user_client.join_chat(invite_url)
                        await asyncio.sleep(3)
                        break  # Success, exit loop
                        
                    except UserAlreadyParticipant:
                        # User is already in channel, this is actually good!
                        print("User already participant - continuing...")
                        await asyncio.sleep(2)
                        break
                        
                    except FloodWait as e:
                        wait_time = e.value
                        if status_msg:
                            await status_msg.edit_text(f"⏳ **Flood wait: Waiting {wait_time} seconds...**")
                        await asyncio.sleep(wait_time + 2)
                        continue  # Try again after waiting
                        
                    except Exception as e:
                        last_error = str(e)
                        print(f"Join attempt {attempt + 1} failed: {last_error}")
                        
                        if attempt == max_retries - 1:
                            await bot_client.stop()
                            return False, f"❌ Join failed: {last_error}"
                        
                        await asyncio.sleep(3)
                        continue
                
                # After joining (or already being a participant), check status
                await asyncio.sleep(2)
                in_channel, current_status = await ensure_user_in_channel()
                
                if not in_channel:
                    await bot_client.stop()
                    return False, "❌ Failed to join channel"
                
                # Promote to admin
                if status_msg:
                    await status_msg.edit_text("👑 **Promoting to admin...**")
                
                try:
                    await bot_client.promote_chat_member(
                        CHANNEL_ID, 
                        user_id,
                        privileges=ChatPrivileges(
                            can_invite_users=True,
                            can_manage_chat=True,
                            can_delete_messages=True,
                            can_post_messages=True,
                            can_edit_messages=True,
                            can_pin_messages=True,
                            can_restrict_members=False,
                            can_promote_members=False,
                            can_manage_video_chats=False
                        )
                    )
                    await asyncio.sleep(2)
                    
                    # Verify
                    assistant_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
                    if assistant_member.status != ChatMemberStatus.ADMINISTRATOR:
                        await bot_client.stop()
                        return False, "❌ Promotion verification failed"
                    
                    await bot_client.stop()
                    return True, "✅ Assistant added and promoted successfully"
                    
                except Exception as e:
                    await bot_client.stop()
                    return False, f"❌ Promotion failed: {str(e)}"
                
        except Exception as e:
            try:
                await bot_client.stop()
            except:
                pass
            return False, f"❌ Setup failed: {str(e)}"
            
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def remove_user_from_channel():
    """Remove user account from channel"""
    try:
        # First check if we're in the channel
        try:
            in_channel, _ = await ensure_user_in_channel()
            if not in_channel:
                return True, "✅ Assistant not in channel"
        except:
            return True, "✅ Assistant not in channel"
        
        # Leave the channel
        try:
            await user_client.leave_chat(CHANNEL_ID)
            return True, "✅ Assistant removed from channel"
        except FloodWait as e:
            print(f"Flood wait on leave: {e.value} seconds")
            return True, f"✅ Assistant will leave automatically (flood wait: {e.value}s)"
        except Exception as e:
            # If we can't leave, it's not critical - continue
            print(f"Warning: Could not leave channel: {e}")
            return True, "⚠️ Could not remove assistant (non-critical)"
            
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

# =====================================================================================
# EBBINGHAUS SCHEDULING - SIMPLIFIED VERSION
# =====================================================================================

@Client.on_message(filters.private & filters.command("neet"))
async def start_scheduling(client, message: Message):
    """Start the simple Ebbinghaus scheduling"""
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    # Check if user wants to schedule media
    if message.reply_to_message and (message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.document):
        user_id = message.from_user.id
        user_states[user_id] = {
            'step': 2,  # Skip to date step
            'post_text': None,
            'media': message.reply_to_message,
            'media_type': 'photo' if message.reply_to_message.photo else 'video' if message.reply_to_message.video else 'document'
        }
        
        today = datetime.datetime.now(IST).date()
        tomorrow = today + timedelta(days=1)
        
        await message.reply_text(
            f"✅ **Media saved!**\n\n"
            f"📅 **Enter start date (YYYY-MM-DD):**\n"
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{tomorrow.strftime('%Y-%m-%d')}`\n\n"
            f"*Posts at 9:00 AM IST*\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="YYYY-MM-DD...")
        )
    else:
        # Text scheduling
        user_id = message.from_user.id
        user_states[user_id] = {
            'step': 1,
            'post_text': None,
            'media': None,
            'media_type': None
        }
        
        await message.reply_text(
            "📘 **Ebbinghaus Review Scheduler**\n\n"
            "Send me the post you want to schedule for 7 reviews at **9:00 AM**.\n\n"
            "**Example:**\n"
            "`• Math: Chapter 1\n• Physics: Mechanics\n• Chemistry: Basics`\n\n"
            "**OR** reply to media with /schedule",
            reply_markup=ForceReply(placeholder="Paste your post here...")
        )

@Client.on_message(filters.private & filters.reply)
async def process_schedule(client, message: Message):
    """Process the schedule inputs"""
    user_id = message.from_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if state['step'] == 1:
        # Store text
        user_states[user_id]['post_text'] = message.text.strip()
        user_states[user_id]['step'] = 2
        
        today = datetime.datetime.now(IST).date()
        tomorrow = today + timedelta(days=1)
        
        await message.reply_text(
            f"✅ **Post saved!**\n\n"
            f"📅 **Enter start date (YYYY-MM-DD):**\n"
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{tomorrow.strftime('%Y-%m-%d')}`\n\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="YYYY-MM-DD...")
        )
        
    elif state['step'] == 2:
        await schedule_posts(client, message, user_id)

async def schedule_posts(client, message: Message, user_id: int):
    """Schedule the posts"""
    date_input = message.text.strip()
    
    try:
        # Parse date
        input_date = datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        
        # Get state
        state = user_states[user_id]
        post_text = state.get('post_text', '')
        media = state.get('media')
        media_type = state.get('media_type')
        
        # Initial status
        status_msg = await message.reply_text("⏳ **Starting scheduler...**")
        
        # Step 1: Initialize user client
        await status_msg.edit_text("👤 **Initializing assistant...**")
        success, assistant_id = await start_user_client()
        if not success:
            await status_msg.edit_text("❌ **Failed to start assistant session**")
            del user_states[user_id]
            return
        
        # Step 2: Set up assistant in channel
        await status_msg.edit_text("🚪 **Setting up assistant in channel...**")
        success, result_msg = await setup_assistant_in_channel(status_msg)
        if not success:
            await status_msg.edit_text(f"❌ **{result_msg}**\n\n"
                                     "**Please ensure:**\n"
                                     "1. Bot is admin in the channel\n"
                                     "2. Bot has 'Invite Users' & 'Add Admins' permissions\n"
                                     "3. The channel ID is correct")
            
            # Stop user client
            try:
                await user_client.stop()
            except:
                pass
            
            del user_states[user_id]
            return
        
        # Show setup success
        await status_msg.edit_text(f"✅ **{result_msg}**\n⏳ **Starting to schedule posts...**")
        await asyncio.sleep(2)
        
        # Step 3: Schedule posts
        intervals = [1, 3, 7, 14, 30, 60, 90]
        review_names = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        
        scheduled_count = 0
        summary_lines = []
        
        for i, day in enumerate(intervals):
            review_date = input_date + timedelta(days=day)
            
            # Create IST time (9:00 AM)
            ist_time = IST.localize(
                datetime.datetime.combine(review_date, datetime.time(9, 0, 0))
            )
            utc_time = ist_time.astimezone(UTC)
            date_formatted = review_date.strftime("%d %B %Y (%A)")
            
            # Create caption
            caption = f"🔄 **{review_names[i]} - Day {day}**\n📅 {date_formatted}\n⏰ 9:00 AM IST"
            if post_text:
                caption += f"\n\n{post_text}"
            
            try:
                # Check date limit
                max_date = datetime.datetime.now(UTC) + timedelta(days=365)
                if utc_time > max_date:
                    summary_lines.append(f"• ❌ **{review_names[i]}:** Beyond 1-year limit")
                    continue
                
                # Schedule the post
                if media:
                    if media_type == 'photo':
                        await user_client.send_photo(
                            CHANNEL_ID,
                            photo=media.photo.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                    elif media_type == 'video':
                        await user_client.send_video(
                            CHANNEL_ID,
                            video=media.video.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                    else:
                        await user_client.send_document(
                            CHANNEL_ID,
                            document=media.document.file_id,
                            caption=caption,
                            schedule_date=utc_time
                        )
                else:
                    await user_client.send_message(
                        CHANNEL_ID,
                        text=caption,
                        schedule_date=utc_time
                    )
                
                scheduled_count += 1
                summary_lines.append(f"• ✅ **{review_names[i]}:** {review_date.strftime('%d %b %Y')}")
                
                # Update progress
                progress = int((i + 1) / len(intervals) * 100)
                progress_bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
                if (i + 1) % 2 == 0 or i == len(intervals) - 1:
                    await status_msg.edit_text(
                        f"📤 **Scheduling:** {i+1}/{len(intervals)}\n"
                        f"`[{progress_bar}]` {progress}%\n"
                        f"Last: {review_names[i]} for {review_date.strftime('%d %b')}"
                    )
                
                # Small delay between posts
                await asyncio.sleep(1.5)
                
            except FloodWait as e:
                await status_msg.edit_text(f"⏳ **Flood wait: Pausing for {e.value}s...**")
                await asyncio.sleep(e.value + 2)
                continue
            except Exception as e:
                error_msg = str(e)
                if any(x in error_msg for x in ["SCHEDULE_DATE_INVALID", "Date too far"]):
                    summary_lines.append(f"• ❌ **{review_names[i]}:** Date error")
                elif "SCHEDULE_TOO_MUCH" in error_msg:
                    summary_lines.append(f"• ❌ **{review_names[i]}:** Too many scheduled")
                else:
                    summary_lines.append(f"• ❌ **{review_names[i]}:** Error")
                await asyncio.sleep(2)
        
        # Step 4: Cleanup
        await status_msg.edit_text("🧹 **Cleaning up...**")
        cleanup_success, cleanup_msg = await remove_user_from_channel()
        
        # Stop user client
        try:
            await user_client.stop()
        except:
            pass
        
        # Clear state
        del user_states[user_id]
        
        # Final summary
        current_time = datetime.datetime.now(IST).strftime('%I:%M %p %Z')
        
        summary = (
            f"📊 **Scheduling Complete**\n\n"
            f"**✅ {scheduled_count}/{len(intervals)} posts scheduled**\n"
            f"**Start Date:** {input_date.strftime('%d %b %Y')}\n"
            f"**Posting Time:** 9:00 AM IST\n"
            f"**Channel:** `{CHANNEL_ID}`\n\n"
            f"**Schedule Summary:**\n" + "\n".join(summary_lines) + f"\n\n"
            f"**Status:** {cleanup_msg}\n"
            f"**Completed at:** {current_time}"
        )
        
        await status_msg.delete()
        await message.reply_text(summary)
        
    except ValueError:
        await message.reply_text(
            "❌ **Invalid date format!**\n"
            "Use **YYYY-MM-DD** format.\n"
            f"*Example: {datetime.datetime.now(IST).date().strftime('%Y-%m-%d')}*"
        )
        if user_id in user_states:
            del user_states[user_id]
    except Exception as e:
        error_msg = str(e)[:200]
        await message.reply_text(f"❌ **Unexpected error:** {error_msg}")
        
        # Cleanup
        try:
            await remove_user_from_channel()
        except:
            pass
        try:
            await user_client.stop()
        except:
            pass
        
        if user_id in user_states:
            del user_states[user_id]
