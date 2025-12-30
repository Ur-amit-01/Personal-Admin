# plugins/Post/schedule.py
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from plugins.helper.db import db
import time
import random
from plugins.helper.time_parser import parse_time, format_time
import asyncio
from datetime import datetime, timedelta
from config import *
from plugins.Post.admin_panel import admin_filter
from plugins.Post.Posting import schedule_deletion, handle_deletion_results, is_restricted_error
import pytz

# ============ CONSTANTS ============ #
IST = pytz.timezone('Asia/Kolkata')

# ============ HELPER FUNCTIONS ============ #
async def parse_schedule_time(time_input: str):
    """Parse schedule time string like '09:00,14:30,18:45' or '9am,2pm,6:30pm'"""
    times = []
    for t in time_input.split(','):
        t = t.strip().lower()
        
        if 'am' in t or 'pm' in t:
            try:
                t_clean = t.replace('am', '').replace('pm', '').strip()
                if ':' in t_clean:
                    hour, minute = t_clean.split(':')
                    hour = int(hour)
                    minute = int(minute)
                else:
                    hour = int(t_clean)
                    minute = 0
                
                if 'pm' in t and hour != 12:
                    hour += 12
                elif 'am' in t and hour == 12:
                    hour = 0
                
                times.append(f"{hour:02d}:{minute:02d}")
            except:
                raise ValueError(f"Invalid time format: {t}")
        
        elif ':' in t:
            try:
                hour, minute = t.split(':')
                hour = int(hour)
                minute = int(minute)
                
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError(f"Invalid time: {t}")
                
                times.append(f"{hour:02d}:{minute:02d}")
            except:
                raise ValueError(f"Invalid time format: {t}")
        else:
            raise ValueError(f"Invalid time format: {t}")
    
    return times

async def get_next_run_time(schedule_times):
    """Get the next scheduled time from now in IST"""
    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime("%H:%M")
    
    sorted_times = sorted(schedule_times)
    
    for schedule_time in sorted_times:
        if schedule_time > current_time_str:
            return schedule_time
    
    return sorted_times[0]

async def calculate_delay_until(schedule_time_str):
    """Calculate seconds until scheduled time in IST"""
    now_utc = datetime.now(pytz.UTC)
    now_ist = now_utc.astimezone(IST)
    
    hour, minute = map(int, schedule_time_str.split(':'))
    scheduled_time_ist = IST.localize(
        datetime(now_ist.year, now_ist.month, now_ist.day, hour, minute, 0)
    )
    
    if scheduled_time_ist < now_ist:
        scheduled_time_ist += timedelta(days=1)
    
    scheduled_time_utc = scheduled_time_ist.astimezone(pytz.UTC)
    delay = (scheduled_time_utc - now_utc).total_seconds()
    return max(1, delay)

async def store_message_in_log_channel(client, message: Message, is_forward=False):
    """Store the message in log channel and return the message ID"""
    try:
        if is_forward:
            log_message = await client.forward_messages(
                chat_id=LOG_CHANNEL,
                from_chat_id=message.chat.id,
                message_ids=message.id
            )
        else:
            log_message = await client.copy_message(
                chat_id=LOG_CHANNEL,
                from_chat_id=message.chat.id,
                message_id=message.id
            )
        return log_message.id
    except Exception as e:
        print(f"Error storing message in log channel: {e}")
        return None

# ============ CORE SCHEDULING FUNCTIONS ============ #
async def execute_scheduled_post(client, schedule_id):
    """Execute a scheduled post using the message from log channel"""
    try:
        schedule = await db.get_schedule(schedule_id)
        if not schedule:
            return
        
        log_message_id = schedule.get("log_message_id")
        group = schedule.get("group", "0")
        is_forward = schedule.get("is_forward", False)
        user_id = schedule.get("user_id")
        delete_after = schedule.get("delete_after")
        schedule_times = schedule.get("schedule_times", [])
        
        if not log_message_id:
            await db.update_schedule(schedule_id, {"last_error": "No log message found"})
            return
        
        channels = await db.get_channels_by_group(group)
        if not channels:
            await db.update_schedule(schedule_id, {"last_error": f"No channels in group {group}"})
            return
        
        post_id = int(time.time())
        sent_messages = []
        success_count = 0
        total_channels = len(channels)
        failed_channels = []
        restricted_channels = []
        deletion_tasks = []
        
        for channel in channels:
            try:
                if is_forward:
                    sent_message = await client.forward_messages(
                        chat_id=channel["channel_id"],
                        from_chat_id=LOG_CHANNEL,
                        message_ids=log_message_id
                    )
                else:
                    sent_message = await client.copy_message(
                        chat_id=channel["channel_id"],
                        from_chat_id=LOG_CHANNEL,
                        message_id=log_message_id
                    )
                
                sent_messages.append({
                    "channel_id": channel["channel_id"],
                    "message_id": sent_message.id,
                    "channel_name": channel.get("name", str(channel["channel_id"]))
                })
                success_count += 1
                
                if delete_after:
                    deletion_tasks.append(
                        schedule_deletion(
                            client,
                            channel["channel_id"],
                            sent_message.id,
                            delete_after,
                            user_id,
                            post_id,
                            channel.get("name", str(channel["channel_id"])),
                            None
                        )
                    )
                    
            except Exception as e:
                error_msg = str(e)
                channel_name = channel.get("name", str(channel["channel_id"]))
                
                if is_restricted_error(error_msg):
                    restricted_channels.append({
                        "channel_id": channel["channel_id"],
                        "channel_name": channel_name,
                        "error": "Restricted/Bot not admin"
                    })
                
                failed_channels.append({
                    "channel_id": channel["channel_id"],
                    "channel_name": channel_name,
                    "error": error_msg[:200]
                })
        
        # Save post data
        post_data = {
            "post_id": post_id,
            "channels": sent_messages,
            "user_id": user_id,
            "created_at": time.time(),
            "is_forward": is_forward,
            "group": group,
            "failed_channels": failed_channels,
            "restricted_channels": restricted_channels,
            "is_scheduled": True,
            "schedule_id": schedule_id,
            "log_message_id": log_message_id
        }
        
        if delete_after:
            post_data["delete_after"] = time.time() + delete_after
            post_data["delete_original"] = True
        
        await db.save_post(post_data)
        
        # Update schedule with last run info
        await db.update_schedule(schedule_id, {
            "last_run": time.time(),
            "last_success": success_count,
            "last_failed": len(failed_channels),
            "last_post_id": post_id,
            "last_error": None
        })
        
        # Log execution
        try:
            log_msg = (
                f"⏰ <blockquote><b>#ScheduledPost Executed | Group {group}</b></blockquote>\n\n"
                f"📌 <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
                f"📌 <b>Post ID:</b> <code>{post_id}</code>\n"
                f"📡 <b>Sent to:</b> {success_count}/{total_channels} channels\n"
                f"🕐 <b>Scheduled Times:</b> {', '.join(schedule_times)}\n"
                f"📋 <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
            )
            
            await client.send_message(chat_id=LOG_CHANNEL, text=log_msg)
        except:
            pass
        
        # Handle deletions if needed
        if delete_after and deletion_tasks:
            asyncio.create_task(
                handle_deletion_results(
                    client=client,
                    deletion_tasks=deletion_tasks,
                    post_id=post_id,
                    delay_seconds=delete_after
                )
            )
        
        # Schedule next execution
        next_time = await get_next_run_time(schedule_times)
        delay_seconds = await calculate_delay_until(next_time)
        
        asyncio.create_task(schedule_next_post(client, schedule_id, delay_seconds))
        
    except Exception as e:
        await db.update_schedule(schedule_id, {"last_error": str(e)[:200]})
        await db.log_error(f"Error executing scheduled post {schedule_id}: {e}")

async def schedule_next_post(client, schedule_id, delay_seconds):
    """Schedule the next execution of a post"""
    await asyncio.sleep(delay_seconds)
    await execute_scheduled_post(client, schedule_id)

async def restore_scheduled_posts(client):
    """Restore scheduled posts when bot starts"""
    try:
        active_schedules = await db.get_active_schedules()
        
        for schedule in active_schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_times = schedule.get("schedule_times", [])
            
            if not schedule_times:
                continue
            
            next_time = await get_next_run_time(schedule_times)
            delay_seconds = await calculate_delay_until(next_time)
            
            asyncio.create_task(schedule_next_post(client, schedule_id, delay_seconds))
            
    except Exception as e:
        await db.log_error(f"Error restoring scheduled posts: {e}")

# ============ COMMAND HANDLERS ============ #
@Client.on_message(filters.command(["schedule", "schedule0", "schedule1", "schedule2", "schedule3"]) & filters.private & admin_filter)
async def schedule_post(client, message: Message):
    """Handle schedule command with schedule name"""
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    if not await db.is_admin(message.from_user.id):
        await message.reply("**❌ You are not authorized to use this command!**")
        return
    
    if not message.reply_to_message:
        await message.reply("**Reply to a message to schedule it.**")
        return
    
    cmd = message.command[0]
    group = "0"
    if len(cmd) > 8:
        group = cmd[-1]
    
    if len(message.command) < 2:
        await message.reply(
            "**❌ Please specify schedule times in IST!**\n\n"
            "**Format:** `/schedule ScheduleName 09:00,14:30,18:45`\n"
            "**Or:** `/schedule ScheduleName 9am,2pm,6:30pm`\n\n"
            "**Example:** `/schedule1 MorningPost 09:00,21:00`\n"
            "**With auto-delete:** `/schedule EveningNews 9am,6pm 2h`"
        )
        return
    
    args = message.text.split()
    
    # First argument after command is schedule name
    if len(args) < 3:
        await message.reply(
            "**❌ Please provide schedule name and times!**\n\n"
            "**Format:** `/schedule ScheduleName 09:00,14:30`\n"
            "**Example:** `/schedule1 DailyUpdate 09:00,21:00`"
        )
        return
    
    schedule_name = args[1]
    time_input = args[2]
    
    delete_after = None
    if len(args) > 3:
        delete_input = ' '.join(args[3:])
        try:
            delete_after = parse_time(delete_input)
            if delete_after <= 0:
                await message.reply("❌ Auto-delete time must be greater than 0")
                return
        except ValueError as e:
            await message.reply(
                f"**❌ Invalid auto-delete time format!**\n\n"
                f"Error: {str(e)}\n\n"
                "**Valid auto-delete formats:**\n"
                "• `2h` (2 hours)\n• `30min` (30 minutes)\n• `1h 30min`\n• `2 days`\n\n"
                "**Example:** `/schedule EveningNews 9am,6pm 2h`"
            )
            return
    
    try:
        schedule_times = await parse_schedule_time(time_input)
    except ValueError as e:
        await message.reply(
            f"**❌ Invalid schedule time format!**\n\n"
            f"Error: {str(e)}\n\n"
            "**Valid formats:**\n"
            "• `09:00,14:30,18:45` (24-hour)\n"
            "• `9am,2pm,6:30pm` (12-hour)\n"
            "**Example:** `/schedule MorningPost 9am,6pm 2h`"
        )
        return
    
    is_forward = message.text.startswith("/fschedule")
    
    processing_msg = await message.reply(
        "**⏰ Saving message to log channel...**",
        reply_to_message_id=message.reply_to_message.id
    )
    
    log_message_id = await store_message_in_log_channel(
        client, 
        message.reply_to_message, 
        is_forward=is_forward
    )
    
    if not log_message_id:
        await processing_msg.edit_text("❌ Failed to save message to log channel.")
        return
    
    schedule_id = int(time.time())
    schedule_data = {
        "schedule_id": schedule_id,
        "schedule_name": schedule_name,
        "user_id": message.from_user.id,
        "group": group,
        "schedule_times": schedule_times,
        "log_message_id": log_message_id,
        "is_forward": is_forward,
        "status": "active",
        "created_at": time.time(),
        "delete_after": delete_after,
        "original_chat_id": message.reply_to_message.chat.id,
        "original_message_id": message.reply_to_message.id
    }
    
    await db.save_schedule(schedule_data)
    
    next_time = await get_next_run_time(schedule_times)
    delay_seconds = await calculate_delay_until(next_time)
    now_ist = datetime.now(IST)
    next_run_str = (now_ist + timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M IST")
    
    asyncio.create_task(schedule_next_post(client, schedule_id, delay_seconds))
    
    result_msg = (
        f"<blockquote>⏰ <b>Post Scheduled!</b></blockquote>\n\n"
        f"• <b>Schedule Name:</b> {schedule_name}\n"
        f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
        f"• <b>Group:</b> {group}\n"
        f"• <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
        f"• <b>Schedule Times:</b> {', '.join(schedule_times)} IST\n"
        f"• <b>Next Run:</b> {next_run_str}\n"
    )
    
    if delete_after:
        time_str = format_time(delete_after)
        result_msg += f"• <b>Auto-delete after:</b> {time_str}\n"
    
    buttons = [
        [InlineKeyboardButton("⏸ Pause", callback_data=f"pause_schedule_{schedule_id}"),
         InlineKeyboardButton("❌ Delete", callback_data=f"delete_schedule_{schedule_id}")],
        [InlineKeyboardButton("📋 List Schedules", callback_data="list_schedules")]
    ]
    
    await processing_msg.edit_text(result_msg, reply_markup=InlineKeyboardMarkup(buttons))
    
    try:
        log_msg = (
            f"⏰ <blockquote><b>#ScheduleCreated | Group {group}</b></blockquote>\n\n"
            f"👤 <b>By:</b> {message.from_user.mention}\n"
            f"📝 <b>Name:</b> {schedule_name}\n"
            f"📌 <b>ID:</b> <code>{schedule_id}</code>\n"
            f"📋 <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
            f"🕐 <b>Times:</b> {', '.join(schedule_times)} IST\n"
            f"⏳ <b>Next Run:</b> {next_run_str}\n"
        )
        await client.send_message(chat_id=LOG_CHANNEL, text=log_msg)
    except:
        pass

@Client.on_message(filters.command(["fschedule", "fschedule0", "fschedule1", "fschedule2", "fschedule3"]) & filters.private & admin_filter)
async def forward_schedule_post(client, message: Message):
    await schedule_post(client, message)

# ============ ENHANCED LIST SCHEDULES FUNCTION ============ #
async def generate_schedule_list(schedules, with_links=True):
    """Generate formatted schedule list with or without hyperlinks"""
    if not schedules:
        return "📋 <b>No schedules found.</b>"
    
    active_schedules = [s for s in schedules if s.get("status") == "active"]
    paused_schedules = [s for s in schedules if s.get("status") == "paused"]
    
    result_msg = "<blockquote>📋 <b>All Schedules</b></blockquote>\n\n"
    
    if active_schedules:
        result_msg += f"<b>▶ Active ({len(active_schedules)}):</b>\n"
        for schedule in active_schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_name = schedule.get("schedule_name", f"Schedule {schedule_id}")
            group = schedule.get("group", "0")
            times = ', '.join(schedule.get("schedule_times", []))
            
            if with_links:
                result_msg += f"  • <a href='t.me/share/url?url=/viewschedule_{schedule_id}'>{schedule_name}</a> | Group {group} | {times} IST\n"
            else:
                result_msg += f"  • {schedule_name} | Group {group} | {times} IST\n"
    
    if paused_schedules:
        result_msg += f"\n<b>⏸ Paused ({len(paused_schedules)}):</b>\n"
        for schedule in paused_schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_name = schedule.get("schedule_name", f"Schedule {schedule_id}")
            group = schedule.get("group", "0")
            times = ', '.join(schedule.get("schedule_times", []))
            
            if with_links:
                result_msg += f"  • <a href='t.me/share/url?url=/viewschedule_{schedule_id}'>{schedule_name}</a> | Group {group} | {times} IST\n"
            else:
                result_msg += f"  • {schedule_name} | Group {group} | {times} IST\n"
    
    return result_msg

# ============ VIEW SCHEDULE COMMAND ============ #
@Client.on_message(filters.command(["viewschedule"]) & filters.private & admin_filter)
async def view_schedule_command(client, message: Message):
    """View detailed information about a specific schedule"""
    if len(message.command) < 2:
        await message.reply("**❌ Please provide a schedule ID!**\n\n**Format:** `/viewschedule schedule_id`")
        return
    
    try:
        schedule_id = int(message.command[1])
    except ValueError:
        await message.reply("**❌ Invalid schedule ID!**")
        return
    
    schedule = await db.get_schedule(schedule_id)
    if not schedule:
        await message.reply("❌ Schedule not found.")
        return
    
    await send_schedule_details(client, message.from_user.id, schedule)

async def send_schedule_details(client, user_id, schedule):
    """Send schedule details with buttons to user"""
    schedule_id = schedule.get("schedule_id")
    schedule_name = schedule.get("schedule_name", f"Schedule {schedule_id}")
    group = schedule.get("group", "0")
    schedule_times = schedule.get("schedule_times", [])
    status = schedule.get("status", "active")
    is_forward = schedule.get("is_forward", False)
    delete_after = schedule.get("delete_after")
    created_at = schedule.get("created_at", time.time())
    
    # Format creation date
    created_str = datetime.fromtimestamp(created_at, IST).strftime("%Y-%m-%d %H:%M IST")
    
    # Get next run time
    if status == "active" and schedule_times:
        next_time = await get_next_run_time(schedule_times)
        delay_seconds = await calculate_delay_until(next_time)
        next_run_str = (datetime.now(IST) + timedelta(seconds=delay_seconds)).strftime("%Y-%m-%d %H:%M IST")
    else:
        next_run_str = "Not scheduled"
    
    # Create message
    details_msg = (
        f"<blockquote>📋 <b>Schedule Details</b></blockquote>\n\n"
        f"📝 <b>Name:</b> {schedule_name}\n"
        f"🆔 <b>ID:</b> <code>{schedule_id}</code>\n"
        f"🏷 <b>Group:</b> {group}\n"
        f"📅 <b>Created:</b> {created_str}\n"
        f"📊 <b>Status:</b> {'▶ Active' if status == 'active' else '⏸ Paused'}\n"
        f"🕐 <b>Times:</b> {', '.join(schedule_times)} IST\n"
        f"⏳ <b>Next Run:</b> {next_run_str}\n"
        f"📋 <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
    )
    
    if delete_after:
        time_str = format_time(delete_after)
        details_msg += f"🗑 <b>Auto-delete:</b> {time_str}\n"
    
    # Create buttons based on status
    if status == "active":
        action_buttons = [
            [InlineKeyboardButton("⏸ Pause Schedule", callback_data=f"pause_schedule_{schedule_id}"),
             InlineKeyboardButton("❌ Delete Schedule", callback_data=f"delete_schedule_{schedule_id}")]
        ]
    else:
        action_buttons = [
            [InlineKeyboardButton("▶ Resume Schedule", callback_data=f"resume_schedule_{schedule_id}"),
             InlineKeyboardButton("❌ Delete Schedule", callback_data=f"delete_schedule_{schedule_id}")]
        ]
    
    # Add navigation buttons
    action_buttons.append(
        [InlineKeyboardButton("📋 Back to List", callback_data="list_schedules")]
    )
    
    try:
        await client.send_message(
            chat_id=user_id,
            text=details_msg,
            reply_markup=InlineKeyboardMarkup(action_buttons)
        )
    except Exception as e:
        print(f"Error sending schedule details: {e}")

# ============ HANDLE HYPERLINKS FROM LIST ============ #
@Client.on_message(filters.regex(r'^/viewschedule_(\d+)$') & filters.private & admin_filter)
async def handle_schedule_link(client, message: Message):
    """Handle hyperlinks from schedule list"""
    match = message.text.split('_')
    if len(match) < 2:
        return
    
    try:
        schedule_id = int(match[1])
    except ValueError:
        return
    
    schedule = await db.get_schedule(schedule_id)
    if not schedule:
        await message.reply("❌ Schedule not found.")
        return
    
    await send_schedule_details(client, message.from_user.id, schedule)

# ============ CALLBACK HANDLERS ============ #
@Client.on_callback_query(filters.regex(r"^pause_schedule_"))
async def pause_schedule_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Pausing schedule...")
    schedule_id = int(callback_query.data.split("_")[2])
    await db.update_schedule(schedule_id, {"status": "paused"})
    
    # Get updated schedule and send details
    schedule = await db.get_schedule(schedule_id)
    if schedule:
        await send_schedule_details(client, callback_query.from_user.id, schedule)

@Client.on_callback_query(filters.regex(r"^resume_schedule_"))
async def resume_schedule_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Resuming schedule...")
    schedule_id = int(callback_query.data.split("_")[2])
    schedule = await db.get_schedule(schedule_id)
    
    if not schedule:
        await callback_query.message.edit_text("❌ Schedule not found.")
        return
    
    await db.update_schedule(schedule_id, {"status": "active"})
    
    # Schedule next execution
    schedule_times = schedule.get("schedule_times", [])
    next_time = await get_next_run_time(schedule_times)
    delay_seconds = await calculate_delay_until(next_time)
    
    asyncio.create_task(schedule_next_post(client, schedule_id, delay_seconds))
    
    # Get updated schedule and send details
    updated_schedule = await db.get_schedule(schedule_id)
    if updated_schedule:
        await send_schedule_details(client, callback_query.from_user.id, updated_schedule)

@Client.on_callback_query(filters.regex(r"^delete_schedule_"))
async def delete_schedule_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Deleting schedule...")
    schedule_id = int(callback_query.data.split("_")[2])
    
    # Get schedule info before deletion
    schedule = await db.get_schedule(schedule_id)
    schedule_name = schedule.get("schedule_name", f"Schedule {schedule_id}") if schedule else f"Schedule {schedule_id}"
    
    await db.delete_schedule(schedule_id)
    
    await callback_query.message.edit_text(
        f"✅ <b>Schedule Deleted</b>\n\n"
        f"📝 <b>Name:</b> {schedule_name}\n"
        f"🆔 <b>ID:</b> <code>{schedule_id}</code>\n\n"
        f"This schedule has been permanently deleted.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Back to List", callback_data="list_schedules")]
        ])
    )

@Client.on_callback_query(filters.regex(r"^list_schedules$"))
async def list_schedules_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Loading schedules...")
    schedules = await db.get_all_schedules()
    
    result_msg = await generate_schedule_list(schedules, with_links=True)
    
    buttons = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="list_schedules")]
    ]
    
    await callback_query.message.edit_text(
        result_msg,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ============ COMMAND FOR LISTING SCHEDULES ============ #
@Client.on_message(filters.command(["listschedules", "schedules"]) & filters.private & admin_filter)
async def list_schedules_command(client, message: Message):
    """Send schedule list with hyperlinks"""
    schedules = await db.get_all_schedules()
    
    result_msg = await generate_schedule_list(schedules, with_links=True)
    
    # Add a helpful note
    result_msg += "\n\n🔗 <i>Click on any schedule name to view details and manage it.</i>"
    
    await message.reply(
        result_msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

