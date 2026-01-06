from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand, ForceReply, ChatPrivileges
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, UserAlreadyParticipant, ChatAdminRequired, PeerIdInvalid
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
# FIXED HELPER FUNCTIONS - PROPER CHANNEL INTERACTION
# =====================================================================================

async def start_user_client():
    """Initialize and start the user client"""
    global user_client
    try:
        user_client = Client(
            "scheduler_user",
            session_string=SESSION_STRING,
            api_id=API_ID,
            api_hash=API_HASH,
            sleep_threshold=60,
            in_memory=True
        )
        await user_client.start()
        user_id = (await user_client.get_me()).id
        print(f"✅ User client started (ID: {user_id})")
        return True, user_id
    except Exception as e:
        print(f"❌ Failed to start user client: {e}")
        return False, None

async def verify_bot_permissions():
    """Verify bot has proper permissions and can access the channel"""
    try:
        # Start bot client
        bot_client = Client("bot_check", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        try:
            # First, try to access the chat to ensure bot is in it
            chat = await bot_client.get_chat(CHANNEL_ID)
            print(f"✅ Bot can access chat: {chat.title}")
            
            # Check bot's member status
            bot_member = await bot_client.get_chat_member(CHANNEL_ID, "me")
            
            if bot_member.status != ChatMemberStatus.ADMINISTRATOR:
                await bot_client.stop()
                return False, "❌ Bot is not an administrator in the channel"
            
            # Check specific permissions
            if not hasattr(bot_member, 'privileges'):
                await bot_client.stop()
                return False, "❌ Bot doesn't have admin privileges"
            
            perms = bot_member.privileges
            missing_perms = []
            
            if not perms.can_invite_users:
                missing_perms.append("Invite Users")
            if not perms.can_promote_members:
                missing_perms.append("Add Admins")
            
            if missing_perms:
                await bot_client.stop()
                return False, f"❌ Bot missing permissions: {', '.join(missing_perms)}"
            
            await bot_client.stop()
            return True, "✅ Bot has all required permissions"
            
        except Exception as e:
            await bot_client.stop()
            return False, f"❌ Bot cannot access channel: {str(e)}"
            
    except Exception as e:
        return False, f"❌ Bot client error: {str(e)}"

async def get_user_channel_status():
    """Get user's current status in channel"""
    try:
        # First ensure user client can access the chat
        try:
            chat = await user_client.get_chat(CHANNEL_ID)
        except Exception as e:
            print(f"User cannot access channel: {e}")
            return False, None, "not_in_channel"
        
        # Get member status
        member = await user_client.get_chat_member(CHANNEL_ID, "me")
        
        status_map = {
            ChatMemberStatus.ADMINISTRATOR: "admin",
            ChatMemberStatus.MEMBER: "member",
            ChatMemberStatus.RESTRICTED: "restricted",
            ChatMemberStatus.LEFT: "left",
            ChatMemberStatus.BANNED: "banned"
        }
        
        status = status_map.get(member.status, "unknown")
        is_admin = member.status == ChatMemberStatus.ADMINISTRATOR
        
        return True, status, is_admin
        
    except Exception as e:
        print(f"Error getting user status: {e}")
        return False, None, False

async def add_user_to_channel_with_bot():
    """Add user to channel using bot - main function"""
    try:
        # Get user ID from user client
        user_id = (await user_client.get_me()).id
        
        # Start bot client
        bot_client = Client("bot_add", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        try:
            # Create an invite link specifically for the user
            invite = await bot_client.create_chat_invite_link(
                CHANNEL_ID,
                name=f"Assistant-{user_id}",
                creates_join_request=False
            )
            invite_url = invite.invite_link
            
            print(f"Created invite link: {invite_url[:50]}...")
            
            # Use user client to join via the link
            await user_client.join_chat(invite_url)
            await asyncio.sleep(3)  # Wait for join to process
            
            # IMPORTANT: Verify the user is now in the channel from bot's perspective
            await asyncio.sleep(2)
            
            try:
                # Try to get the user's member info from bot's perspective
                user_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
                print(f"User status from bot POV: {user_member.status}")
                
                # Now promote the user
                await bot_client.promote_chat_member(
                    CHANNEL_ID,
                    user_id,
                    privileges=ChatPrivileges(
                        can_post_messages=True,
                        can_edit_messages=True,
                        can_delete_messages=True,
                        can_invite_users=True,
                        can_restrict_members=False,
                        can_promote_members=False,
                        can_change_info=False,
                        can_pin_messages=True,
                        can_manage_video_chats=False
                    )
                )
                
                await asyncio.sleep(2)
                
                # Verify promotion
                user_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
                if user_member.status == ChatMemberStatus.ADMINISTRATOR:
                    await bot_client.stop()
                    return True, "✅ Assistant added and promoted successfully"
                else:
                    await bot_client.stop()
                    return False, "❌ Promotion verification failed"
                    
            except PeerIdInvalid:
                await bot_client.stop()
                return False, "❌ Bot cannot recognize user in channel (PeerIdInvalid). User may need to wait or try again."
            except Exception as e:
                await bot_client.stop()
                return False, f"❌ Promotion error: {str(e)}"
                
        except FloodWait as e:
            await bot_client.stop()
            return False, f"❌ Flood wait: Please try again in {e.value} seconds"
        except Exception as e:
            await bot_client.stop()
            return False, f"❌ Error: {str(e)}"
            
    except Exception as e:
        try:
            await bot_client.stop()
        except:
            pass
        return False, f"❌ Setup error: {str(e)}"

async def promote_existing_member():
    """Promote an existing member to admin"""
    try:
        user_id = (await user_client.get_me()).id
        
        bot_client = Client("bot_promote", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
        await bot_client.start()
        
        try:
            # First verify user is in channel from bot's perspective
            user_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
            print(f"Current user status: {user_member.status}")
            
            if user_member.status == ChatMemberStatus.ADMINISTRATOR:
                await bot_client.stop()
                return True, "✅ Assistant is already admin"
            
            # Promote user
            await bot_client.promote_chat_member(
                CHANNEL_ID,
                user_id,
                privileges=ChatPrivileges(
                    can_post_messages=True,
                    can_edit_messages=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_restrict_members=False,
                    can_promote_members=False,
                    can_change_info=False,
                    can_pin_messages=True,
                    can_manage_video_chats=False
                )
            )
            
            await asyncio.sleep(2)
            
            # Verify
            user_member = await bot_client.get_chat_member(CHANNEL_ID, user_id)
            if user_member.status == ChatMemberStatus.ADMINISTRATOR:
                await bot_client.stop()
                return True, "✅ Assistant promoted to admin"
            else:
                await bot_client.stop()
                return False, "❌ Promotion verification failed"
                
        except PeerIdInvalid:
            await bot_client.stop()
            return False, "❌ Bot cannot see user in channel. Try removing and re-adding the assistant."
        except Exception as e:
            await bot_client.stop()
            return False, f"❌ Promotion failed: {str(e)}"
            
    except Exception as e:
        try:
            await bot_client.stop()
        except:
            pass
        return False, f"❌ Error: {str(e)}"

async def setup_assistant(status_msg=None):
    """Main setup function for assistant"""
    try:
        # Step 1: Check bot permissions
        if status_msg:
            await status_msg.edit_text("🔍 **Verifying bot permissions...**")
        
        bot_ok, bot_msg = await verify_bot_permissions()
        if not bot_ok:
            return False, bot_msg
        
        # Step 2: Check user's current status
        if status_msg:
            await status_msg.edit_text("🔍 **Checking assistant status...**")
        
        can_access, status, is_admin = await get_user_channel_status()
        
        if can_access and is_admin:
            return True, "✅ Assistant is already admin"
        
        # Step 3: Different paths based on current status
        if status == "not_in_channel":
            if status_msg:
                await status_msg.edit_text("🚪 **Adding assistant to channel...**")
            
            # User not in channel, need to add them
            success, msg = await add_user_to_channel_with_bot()
            return success, msg
            
        elif status in ["member", "restricted"]:
            if status_msg:
                await status_msg.edit_text("👑 **Promoting assistant to admin...**")
            
            # User is member but not admin, promote them
            success, msg = await promote_existing_member()
            return success, msg
            
        else:
            return False, f"❌ Assistant status unknown or problematic: {status}"
            
    except Exception as e:
        return False, f"❌ Setup failed: {str(e)}"

async def cleanup_assistant():
    """Clean up assistant from channel"""
    try:
        # Check if we're in the channel
        can_access, status, _ = await get_user_channel_status()
        
        if not can_access or status in ["left", "not_in_channel", "banned"]:
            return True, "✅ Assistant not in channel"
        
        # Leave the channel
        try:
            await user_client.leave_chat(CHANNEL_ID)
            return True, "✅ Assistant removed from channel"
        except FloodWait as e:
            return True, f"✅ Assistant will auto-leave (waiting {e.value}s)"
        except Exception as e:
            print(f"Warning on leave: {e}")
            return True, "⚠️ Could not remove assistant (non-critical)"
            
    except Exception as e:
        return False, f"❌ Cleanup error: {str(e)}"

# =====================================================================================
# SIMPLIFIED SCHEDULING FUNCTION
# =====================================================================================

@Client.on_message(filters.private & filters.command("neet"))
async def start_scheduling(client, message: Message):
    """Start the scheduling process"""
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    # Check if media scheduling
    if message.reply_to_message and (message.reply_to_message.photo or message.reply_to_message.video or message.reply_to_message.document):
        user_id = message.from_user.id
        user_states[user_id] = {
            'step': 2,
            'post_text': None,
            'media': message.reply_to_message,
            'media_type': 'photo' if message.reply_to_message.photo else 'video' if message.reply_to_message.video else 'document'
        }
        
        today = datetime.datetime.now(IST).date()
        
        await message.reply_text(
            f"✅ **Media saved!**\n\n"
            f"📅 **Enter start date (YYYY-MM-DD):**\n"
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{(today + timedelta(days=1)).strftime('%Y-%m-%d')}`\n\n"
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
            "`• Subject: Topic 1\n• Another: Topic 2`\n\n"
            "**OR** reply to media with /schedule",
            reply_markup=ForceReply(placeholder="Paste your post here...")
        )

@Client.on_message(filters.private & filters.reply)
async def process_schedule(client, message: Message):
    """Process schedule inputs"""
    user_id = message.from_user.id
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if state['step'] == 1:
        user_states[user_id]['post_text'] = message.text.strip()
        user_states[user_id]['step'] = 2
        
        today = datetime.datetime.now(IST).date()
        
        await message.reply_text(
            f"✅ **Post saved!**\n\n"
            f"📅 **Enter start date (YYYY-MM-DD):**\n"
            f"• Today: `{today.strftime('%Y-%m-%d')}`\n"
            f"• Tomorrow: `{(today + timedelta(days=1)).strftime('%Y-%m-%d')}`\n\n"
            f"*Example: {today.strftime('%Y-%m-%d')}*",
            reply_markup=ForceReply(placeholder="YYYY-MM-DD...")
        )
        
    elif state['step'] == 2:
        await execute_scheduling(client, message, user_id)

async def execute_scheduling(client, message: Message, user_id: int):
    """Execute the scheduling process"""
    date_input = message.text.strip()
    
    try:
        # Parse date
        input_date = datetime.datetime.strptime(date_input, "%Y-%m-%d").date()
        
        # Get state
        state = user_states[user_id]
        post_text = state.get('post_text', '')
        media = state.get('media')
        media_type = state.get('media_type')
        
        # Status message
        status_msg = await message.reply_text("⏳ **Starting...**")
        
        # Step 1: Initialize user client
        await status_msg.edit_text("👤 **Initializing assistant...**")
        success, assistant_id = await start_user_client()
        if not success:
            await status_msg.edit_text("❌ **Failed to initialize assistant**")
            del user_states[user_id]
            return
        
        # Step 2: Setup assistant in channel
        await status_msg.edit_text("🚀 **Setting up assistant...**")
        success, setup_msg = await setup_assistant(status_msg)
        
        if not success:
            await status_msg.edit_text(f"❌ **Setup failed**\n\n{setup_msg}\n\n"
                                     "**Please ensure:**\n"
                                     "1. Bot is admin with all permissions\n"
                                     "2. Channel ID is correct\n"
                                     "3. Try removing assistant manually first")
            
            try:
                await user_client.stop()
            except:
                pass
            
            del user_states[user_id]
            return
        
        # Step 3: Schedule posts
        await status_msg.edit_text(f"✅ **{setup_msg}**\n📤 **Starting to schedule...**")
        await asyncio.sleep(2)
        
        intervals = [1, 3, 7, 14, 30, 60, 90]
        review_names = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        
        scheduled = 0
        results = []
        
        for i, day in enumerate(intervals):
            review_date = input_date + timedelta(days=day)
            
            # Create time
            ist_time = IST.localize(datetime.datetime.combine(review_date, datetime.time(9, 0, 0)))
            utc_time = ist_time.astimezone(UTC)
            
            # Create caption
            caption = f"🔄 **{review_names[i]} - Day {day}**\n📅 {review_date.strftime('%d %B %Y (%A)')}\n⏰ 9:00 AM IST"
            if post_text:
                caption += f"\n\n{post_text}"
            
            try:
                # Check date limit
                max_date = datetime.datetime.now(UTC) + timedelta(days=365)
                if utc_time > max_date:
                    results.append(f"• ❌ **{review_names[i]}:** Beyond limit")
                    continue
                
                # Schedule
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
                
                scheduled += 1
                results.append(f"• ✅ **{review_names[i]}:** {review_date.strftime('%d %b')}")
                
                # Update progress
                if (i + 1) % 2 == 0 or i == len(intervals) - 1:
                    progress = int((i + 1) / len(intervals) * 100)
                    bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
                    await status_msg.edit_text(
                        f"📤 **Progress:** {i+1}/{len(intervals)}\n"
                        f"`[{bar}]` {progress}%\n"
                        f"Last: {review_names[i]}"
                    )
                
                await asyncio.sleep(1)
                
            except FloodWait as e:
                await status_msg.edit_text(f"⏳ **Waiting {e.value}s...**")
                await asyncio.sleep(e.value + 2)
                continue
            except Exception as e:
                err = str(e)
                if "SCHEDULE_DATE_INVALID" in err:
                    results.append(f"• ❌ **{review_names[i]}:** Date invalid")
                elif "SCHEDULE_TOO_MUCH" in err:
                    results.append(f"• ❌ **{review_names[i]}:** Too many")
                else:
                    results.append(f"• ❌ **{review_names[i]}:** Error")
                await asyncio.sleep(2)
        
        # Step 4: Cleanup
        await status_msg.edit_text("🧹 **Cleaning up...**")
        cleanup_ok, cleanup_msg = await cleanup_assistant()
        
        # Stop client
        try:
            await user_client.stop()
        except:
            pass
        
        # Clear state
        del user_states[user_id]
        
        # Final message
        current_time = datetime.datetime.now(IST).strftime('%I:%M %p %Z')
        
        summary = (
            f"📊 **Scheduling Complete**\n\n"
            f"**✅ {scheduled}/{len(intervals)} posts scheduled**\n"
            f"**Start:** {input_date.strftime('%d %b %Y')}\n"
            f"**Time:** 9:00 AM IST\n"
            f"**Channel:** `{CHANNEL_ID}`\n\n"
            f"**Results:**\n" + "\n".join(results) + f"\n\n"
            f"**Cleanup:** {cleanup_msg}\n"
            f"**Completed:** {current_time}"
        )
        
        await status_msg.delete()
        await message.reply_text(summary)
        
    except ValueError:
        await message.reply_text(
            "❌ **Invalid date!** Use YYYY-MM-DD\n"
            f"*Example: {datetime.datetime.now(IST).date().strftime('%Y-%m-%d')}*"
        )
        if user_id in user_states:
            del user_states[user_id]
    except Exception as e:
        await message.reply_text(f"❌ **Error:** {str(e)[:200]}")
        
        try:
            await cleanup_assistant()
        except:
            pass
        try:
            await user_client.stop()
        except:
            pass
        
        if user_id in user_states:
            del user_states[user_id]
