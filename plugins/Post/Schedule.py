# plugins/Post/schedule.py
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from plugins.helper.db import db
import time
import random
from plugins.helper.time_parser import parse_time, format_time
import asyncio
from datetime import datetime, timedelta
import pytz
from config import *
from plugins.Post.admin_panel import admin_filter
from plugins.Post.Posting import schedule_deletion, handle_deletion_results, is_restricted_error

# ============ TIMEZONE CONFIG ============ #
# Using Indian Standard Time (IST)
IST = pytz.timezone('Asia/Kolkata')

# ============ HELPER FUNCTIONS ============ #
async def parse_schedule_time(time_input: str):
    """Parse schedule time string like '09:00,14:30,18:45' or '9am,2pm,6:30pm'"""
    times = []
    for t in time_input.split(','):
        t = t.strip().lower()
        
        # Handle formats like "9am", "2pm"
        if 'am' in t or 'pm' in t:
            try:
                # Remove am/pm and any spaces
                t_clean = t.replace('am', '').replace('pm', '').strip()
                if ':' in t_clean:
                    hour, minute = t_clean.split(':')
                    hour = int(hour)
                    minute = int(minute)
                else:
                    hour = int(t_clean)
                    minute = 0
                
                # Adjust for pm
                if 'pm' in t and hour != 12:
                    hour += 12
                # Adjust for 12am
                elif 'am' in t and hour == 12:
                    hour = 0
                
                times.append(f"{hour:02d}:{minute:02d}")
            except:
                raise ValueError(f"Invalid time format: {t}")
        
        # Handle 24-hour format like "09:00", "14:30"
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
    # Get current time in IST
    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime("%H:%M")
    
    # Sort times
    sorted_times = sorted(schedule_times)
    
    # Find next time today
    for schedule_time in sorted_times:
        if schedule_time > current_time_str:
            return schedule_time
    
    # If no more times today, use first time tomorrow
    return sorted_times[0]

async def calculate_delay_until(schedule_time_str):
    """Calculate seconds until scheduled time in IST"""
    # Get current time in IST
    now_ist = datetime.now(IST)
    
    # Parse scheduled time
    hour, minute = map(int, schedule_time_str.split(':'))
    
    # Create scheduled time in IST today
    scheduled_time_ist = now_ist.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # If scheduled time is in the past today, schedule for tomorrow
    if scheduled_time_ist < now_ist:
        scheduled_time_ist += timedelta(days=1)
    
    # Calculate delay in seconds
    delay = (scheduled_time_ist - now_ist).total_seconds()
    return max(1, delay)  # Ensure at least 1 second

def debug_print(msg):
    """Debug print with IST timestamp"""
    now_ist = datetime.now(IST)
    timestamp = now_ist.strftime("%H:%M:%S")
    print(f"[{timestamp} IST] [SCHEDULE] {msg}")

# ============ CORE SCHEDULING FUNCTIONS ============ #
async def store_message_in_log_channel(client, message: Message, is_forward=False):
    """Store the message in log channel and return the message ID"""
    try:
        debug_print(f"Storing message in log channel. Is forward: {is_forward}")
        
        if is_forward:
            # Forward the message to log channel
            log_message = await client.forward_messages(
                chat_id=LOG_CHANNEL,
                from_chat_id=message.chat.id,
                message_ids=message.id
            )
        else:
            # Copy the message to log channel
            log_message = await client.copy_message(
                chat_id=LOG_CHANNEL,
                from_chat_id=message.chat.id,
                message_id=message.id
            )
        
        debug_print(f"Message stored in log channel with ID: {log_message.id}")
        return log_message.id
    except Exception as e:
        debug_print(f"Error storing message in log channel: {e}")
        return None

async def execute_scheduled_post(client, schedule_id):
    """Execute a scheduled post using the message from log channel"""
    try:
        debug_print(f"Starting execution of schedule {schedule_id}")
        
        # Get schedule from database
        schedule = await db.get_schedule(schedule_id)
        if not schedule:
            debug_print(f"Schedule {schedule_id} not found in database")
            return
        
        schedule_name = schedule.get("name", f"Schedule {schedule_id}")
        log_message_id = schedule.get("log_message_id")
        group = schedule.get("group", "0")
        is_forward = schedule.get("is_forward", False)
        user_id = schedule.get("user_id")
        delete_after = schedule.get("delete_after")
        schedule_times = schedule.get("schedule_times", [])
        
        if not log_message_id:
            debug_print(f"Schedule {schedule_id}: No log message ID found")
            await db.update_schedule(schedule_id, {"last_error": "No log message found"})
            return
        
        debug_print(f"Schedule {schedule_id}: Got log message ID {log_message_id} for group {group}")
        
        # Get channels for the group
        channels = await db.get_channels_by_group(group)
        if not channels:
            debug_print(f"Schedule {schedule_id}: No channels in group {group}")
            await db.update_schedule(schedule_id, {"last_error": f"No channels in group {group}"})
            return
        
        debug_print(f"Schedule {schedule_id}: Found {len(channels)} channels in group {group}")
        
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
                    debug_print(f"Forwarding to channel {channel.get('name', channel['channel_id'])}")
                    # Forward from log channel
                    sent_message = await client.forward_messages(
                        chat_id=channel["channel_id"],
                        from_chat_id=LOG_CHANNEL,
                        message_ids=log_message_id
                    )
                else:
                    debug_print(f"Copying to channel {channel.get('name', channel['channel_id'])}")
                    # Copy from log channel
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
                            None  # No confirmation message for scheduled posts
                        )
                    )
                    
            except Exception as e:
                error_msg = str(e)
                channel_name = channel.get("name", str(channel["channel_id"]))
                
                is_restricted = is_restricted_error(error_msg)
                
                channel_data = {
                    "channel_id": channel["channel_id"],
                    "channel_name": channel_name,
                    "error": error_msg[:200],
                    "is_restricted": is_restricted,
                    "full_error": error_msg
                }
                
                if is_restricted:
                    restricted_channels.append({
                        "channel_id": channel["channel_id"],
                        "channel_name": channel_name,
                        "error": "Restricted/Bot not admin"
                    })
                
                failed_channels.append(channel_data)
                debug_print(f"Failed to send to {channel_name}: {error_msg[:50]}")
        
        debug_print(f"Schedule {schedule_id}: Successfully sent to {success_count}/{total_channels} channels")
        
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
            "log_message_id": log_message_id,
            "schedule_name": schedule_name
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
            "last_error": None  # Clear any previous error
        })
        
        # Log the scheduled post execution
        try:
            # Get current IST time for log
            now_ist = datetime.now(IST)
            current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
            
            log_msg = (
                f"⏰ <blockquote><b>#ScheduledPost Executed | Group {group}</b></blockquote>\n\n"
                f"📌 <b>Schedule Name:</b> {schedule_name}\n"
                f"📌 <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
                f"📌 <b>Post ID:</b> <code>{post_id}</code>\n"
                f"⏰ <b>Executed At:</b> {current_time_str}\n"
                f"📡 <b>Sent to:</b> {success_count}/{total_channels} channels\n"
                f"🕐 <b>Scheduled Times:</b> {', '.join(schedule_times)} IST\n"
                f"📋 <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
            )
            
            if delete_after:
                log_msg += f"🗑 <b>Auto-delete after:</b> {format_time(delete_after)}\n"
            
            if failed_channels:
                log_msg += f"\n❌ <b>Failed Channels ({len(failed_channels)}):</b>\n"
                for channel in failed_channels[:10]:
                    error_type = "RESTRICTED" if channel.get("is_restricted") else "ERROR"
                    log_msg += f"  - {channel['channel_name']}: {error_type}\n"
            
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=log_msg
            )
            debug_print(f"Schedule {schedule_id}: Execution logged in log channel")
        except Exception as e:
            debug_print(f"Error logging scheduled post execution: {e}")
        
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
        
        # Show next run in IST
        next_run_ist = datetime.now(IST) + timedelta(seconds=delay_seconds)
        next_run_str = next_run_ist.strftime("%Y-%m-%d %H:%M IST")
        
        debug_print(f"Schedule {schedule_id}: Next execution scheduled for {next_run_str} (in {delay_seconds} seconds)")
        
        asyncio.create_task(
            schedule_next_post(client, schedule_id, delay_seconds)
        )
        
    except Exception as e:
        error_msg = f"Error executing scheduled post {schedule_id}: {e}"
        debug_print(error_msg)
        await db.update_schedule(schedule_id, {"last_error": str(e)[:200]})
        await db.log_error(error_msg)

async def schedule_next_post(client, schedule_id, delay_seconds):
    """Schedule the next execution of a post"""
    debug_print(f"Schedule {schedule_id}: Waiting {delay_seconds} seconds for next execution")
    await asyncio.sleep(delay_seconds)
    debug_print(f"Schedule {schedule_id}: Time reached, executing now")
    await execute_scheduled_post(client, schedule_id)

async def restore_scheduled_posts(client):
    """Restore scheduled posts when bot starts"""
    try:
        debug_print("Restoring scheduled posts...")
        schedules = await db.get_all_schedules()
        debug_print(f"Found {len(schedules)} schedules")
        
        for schedule in schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_times = schedule.get("schedule_times", [])
            
            if not schedule_times:
                debug_print(f"Schedule {schedule_id}: No schedule times, skipping")
                continue
            
            # Calculate delay until next scheduled time in IST
            next_time = await get_next_run_time(schedule_times)
            delay_seconds = await calculate_delay_until(next_time)
            
            # Show next run in IST
            next_run_ist = datetime.now(IST) + timedelta(seconds=delay_seconds)
            next_run_str = next_run_ist.strftime("%Y-%m-%d %H:%M IST")
            
            debug_print(f"Schedule {schedule_id}: Next execution at {next_run_str} (in {delay_seconds} seconds)")
            
            # Schedule next execution
            asyncio.create_task(
                schedule_next_post(client, schedule_id, delay_seconds)
            )
            
        debug_print("All schedules restored")
            
    except Exception as e:
        error_msg = f"Error restoring scheduled posts: {e}"
        debug_print(error_msg)
        await db.log_error(error_msg)

# ============ COMMAND HANDLERS ============ #
@Client.on_message(filters.command(["schedule", "schedule0", "schedule1", "schedule2", "schedule3"]) & filters.private & admin_filter)
async def schedule_post(client, message: Message):
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
    
    # Determine which group to post to
    cmd = message.command[0]
    group = "0"  # Default group
    if len(cmd) > 8:  # For schedule1, schedule2, schedule3
        group = cmd[-1]
    
    # Parse the command arguments
    args = message.text.split()
    
    if len(args) < 2:
        await message.reply(
            "**❌ Please specify schedule times and name!**\n\n"
            "**Format:** `/schedule \"Schedule Name\" 09:00,14:30,18:45`\n"
            "**Or:** `/schedule \"My Daily Posts\" 9am,2pm,6:30pm`\n\n"
            "**Note:** Times are in IST (Indian Standard Time)\n\n"
            "**Example:** `/schedule1 \"Morning Posts\" 09:00,21:00`\n"
            "**Example:** `/schedule2 \"Evening Updates\" 8am,12pm,4pm,8pm`\n\n"
            "**With auto-delete:** `/schedule \"Temp Posts\" 9am,6pm 2h`\n"
            "**With auto-delete:** `/schedule \"Hourly News\" 09:00,21:00 30min`"
        )
        return
    
    # Extract schedule name (quoted or first word)
    schedule_name = ""
    time_input_start = 1
    
    # Check if first argument is quoted
    if args[1].startswith('"'):
        # Find the closing quote
        full_text = ' '.join(args[1:])
        if '"' in full_text[1:]:
            end_quote_idx = full_text.find('"', 1)
            schedule_name = full_text[1:end_quote_idx]
            remaining_args = full_text[end_quote_idx+1:].strip().split()
            if remaining_args:
                time_input = remaining_args[0]
                time_input_start = 0
            else:
                await message.reply("**❌ Please specify schedule times after the name!**")
                return
        else:
            await message.reply("**❌ Missing closing quote for schedule name!**")
            return
    else:
        # Use first word as name (without quotes)
        schedule_name = args[1]
        if len(args) < 3:
            await message.reply("**❌ Please specify schedule times!**")
            return
        time_input = args[2]
        time_input_start = 2
    
    # Check for auto-delete time
    delete_after = None
    if len(args) > time_input_start + 1:
        # Join all remaining arguments for auto-delete time
        delete_input = ' '.join(args[time_input_start + 1:])
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
                "• `30s` (30 seconds)\n"
                "• `5min` (5 minutes)\n"
                "• `2h` (2 hours)\n"
                "• `1h30m` (1 hour 30 minutes)\n"
                "• `1 day 2 hours` (1 day 2 hours)\n\n"
                "**Full examples:**\n"
                "• `/schedule \"My Schedule\" 9am,6pm 2h`\n"
                "• `/schedule \"Daily Posts\" 09:00,21:00 30min`\n"
                "• `/schedule \"Updates\" 8am,12pm,8pm 1h15m`"
            )
            return
    
    # Parse schedule times
    try:
        schedule_times = await parse_schedule_time(time_input)
    except ValueError as e:
        await message.reply(
            f"**❌ Invalid schedule time format!**\n\n"
            f"Error: {str(e)}\n\n"
            "**Valid schedule formats (IST Time):**\n"
            "• `09:00,14:30,18:45` (24-hour)\n"
            "• `9am,2pm,6:30pm` (12-hour)\n"
            "• `08:00,12:00,16:00,20:00`\n"
            "• `5:54pm` (single time)\n\n"
            "**With schedule name:**\n"
            "• `/schedule \"Morning Posts\" 9am,6pm 2h`\n"
            "• `/schedule \"Daily Updates\" 09:00,21:00 1h 30min`\n"
            "• `/schedule \"News\" 8am,12pm,8pm 45min`"
        )
        return
    
    # Check if this is a forward schedule
    is_forward = message.text.startswith("/fschedule")
    debug_print(f"Creating {'forward' if is_forward else 'copy'} schedule for group {group}")
    
    # Store message in log channel
    processing_msg = await message.reply(
        f"**⏰ Saving message to log channel...**",
        reply_to_message_id=message.reply_to_message.id
    )
    
    log_message_id = await store_message_in_log_channel(
        client, 
        message.reply_to_message, 
        is_forward=is_forward
    )
    
    if not log_message_id:
        await processing_msg.edit_text("❌ Failed to save message to log channel. Check bot permissions.")
        return
    
    # Create schedule
    schedule_id = int(time.time())
    schedule_data = {
        "schedule_id": schedule_id,
        "name": schedule_name,
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
    
    # Save schedule to database
    await db.save_schedule(schedule_data)
    
    # Calculate next run time in IST
    next_time = await get_next_run_time(schedule_times)
    delay_seconds = await calculate_delay_until(next_time)
    
    # Show next run in IST
    next_run_ist = datetime.now(IST) + timedelta(seconds=delay_seconds)
    next_run_str = next_run_ist.strftime("%Y-%m-%d %H:%M IST")
    
    # Schedule the first post
    debug_print(f"Scheduling first post for schedule {schedule_id} in {delay_seconds} seconds")
    asyncio.create_task(
        schedule_next_post(client, schedule_id, delay_seconds)
    )
    
    # Send confirmation
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
    
    # Add management buttons
    buttons = [
        [InlineKeyboardButton("❌ Delete Schedule", callback_data=f"confirm_delete_{schedule_id}")],
        [InlineKeyboardButton("📋 List Schedules", callback_data="list_schedules")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await processing_msg.edit_text(result_msg)
    #await processing_msg.edit_text(result_msg, reply_markup=reply_markup)
    
    # Log to log channel
    try:
        now_ist = datetime.now(IST)
        current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        
        log_msg = (
            f"⏰ <blockquote><b>#ScheduleCreated | Group {group}</b></blockquote>\n\n"
            f"👤 <b>Scheduled By:</b> {message.from_user.mention}\n"
            f"🕐 <b>Scheduled At:</b> {current_time_str}\n"
            f"📌 <b>Schedule Name:</b> {schedule_name}\n"
            f"📌 <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
            f"📋 <b>Type:</b> {'Forward' if is_forward else 'Copy'}\n"
            f"🕐 <b>Times:</b> {', '.join(schedule_times)} IST\n"
            f"⏳ <b>Next Run:</b> {next_run_str}\n"
        )
        
        if delete_after:
            log_msg += f"🗑 <b>Auto-delete after:</b> {format_time(delete_after)}\n"
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_msg
        )
    except Exception as e:
        debug_print(f"Error sending schedule log: {e}")
    
    debug_print(f"Schedule {schedule_id} created successfully")

# Forward schedule command (different command but same logic)
@Client.on_message(filters.command(["fschedule", "fschedule0", "fschedule1", "fschedule2", "fschedule3"]) & filters.private & admin_filter)
async def forward_schedule_post(client, message: Message):
    # The schedule_post function will detect it's a forward from the command
    await schedule_post(client, message)

# ============ CALLBACK HANDLERS ============ #
@Client.on_callback_query(filters.regex(r"^confirm_delete_"))
async def confirm_delete_handler(client, callback_query: CallbackQuery):
    schedule_id = int(callback_query.data.split("_")[2])
    
    # Get schedule info for confirmation
    schedule = await db.get_schedule(schedule_id)
    
    if not schedule:
        await callback_query.answer("Schedule not found!", show_alert=True)
        await callback_query.message.edit_text("❌ Schedule not found.")
        return
    
    schedule_name = schedule.get("name", f"Schedule {schedule_id}")
    group = schedule.get("group", "0")
    times = ', '.join(schedule.get("schedule_times", []))
    
    # Ask for confirmation
    await callback_query.answer("Confirm deletion...")
    
    confirm_msg = (
        f"⚠️ <b>Confirm Schedule Deletion</b>\n\n"
        f"• <b>Schedule Name:</b> {schedule_name}\n"
        f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
        f"• <b>Group:</b> {group}\n"
        f"• <b>Times:</b> {times} IST\n\n"
        f"Are you sure you want to delete this schedule?"
    )
    
    await callback_query.message.edit_text(
        confirm_msg,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"delete_yes_{schedule_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"delete_no_{schedule_id}")
            ]
        ])
    )

@Client.on_callback_query(filters.regex(r"^delete_yes_"))
async def delete_yes_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Deleting schedule...")
    
    schedule_id = int(callback_query.data.split("_")[2])
    
    # Get schedule info before deleting
    schedule = await db.get_schedule(schedule_id)
    
    # Delete schedule from database
    await db.delete_schedule(schedule_id)
    
    if schedule:
        schedule_name = schedule.get("name", f"Schedule {schedule_id}")
        await callback_query.message.edit_text(
            f"✅ <b>Schedule Deleted</b>\n\n"
            f"• <b>Schedule Name:</b> {schedule_name}\n"
            f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n\n"
            f"This schedule will no longer run."
        )
    else:
        await callback_query.message.edit_text(
            f"✅ <b>Schedule Deleted</b>\n\n"
            f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n\n"
            f"This schedule will no longer run."
        )
    
    # Log deletion
    try:
        now_ist = datetime.now(IST)
        current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        
        log_msg = (
            f"🗑 <blockquote><b>#ScheduleDeleted</b></blockquote>\n\n"
            f"👤 <b>Deleted By:</b> {callback_query.from_user.mention}\n"
            f"🕐 <b>Deleted At:</b> {current_time_str}\n"
            f"📌 <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
        )
        
        if schedule:
            log_msg += f"📝 <b>Schedule Name:</b> {schedule.get('name', f'Schedule {schedule_id}')}\n"
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_msg
        )
    except:
        pass

@Client.on_callback_query(filters.regex(r"^delete_no_"))
async def delete_no_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Deletion cancelled")
    # Go back to schedule list
    await list_schedules_handler(client, callback_query)

@Client.on_callback_query(filters.regex(r"^list_schedules$"))
async def list_schedules_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Loading schedules...")
    
    # Get all schedules
    schedules = await db.get_all_schedules()
    
    if not schedules:
        await callback_query.message.edit_text("📋 <b>No schedules found.</b>")
        return
    
    # Group schedules by group
    schedule_groups = {}
    for schedule in schedules:
        group = schedule.get("group", "0")
        if group not in schedule_groups:
            schedule_groups[group] = []
        schedule_groups[group].append(schedule)
    
    # Get current IST time for header
    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    
    result_msg = f"<blockquote>📋 <b>All Schedules</b></blockquote>\n"
    result_msg += f"<i>Current Time: {current_time_str}</i>\n\n"
    
    # Sort groups
    for group in sorted(schedule_groups.keys()):
        group_schedules = schedule_groups[group]
        result_msg += f"<b>📌 Group {group} ({len(group_schedules)}):</b>\n"
        
        for schedule in group_schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_name = schedule.get("name", f"Schedule {schedule_id}")
            times = ', '.join(schedule.get("schedule_times", []))[:30]
            
            # Add delete info if exists
            delete_info = ""
            if schedule.get("delete_after"):
                delete_info = f" | 🗑 {format_time(schedule.get('delete_after'))}"
            
            result_msg += f"  • <b>{schedule_name}</b>\n"
            result_msg += f"  • ID: <code>{schedule_id}</code> | Times: {times} {delete_info}\n"
        
        result_msg += "\n"
    
    buttons = []
    
    # Create buttons: Left button with schedule name (does nothing), Right button with delete icon
    for group in sorted(schedule_groups.keys()):
        group_schedules = schedule_groups[group]
        for schedule in group_schedules:
            schedule_id = schedule.get("schedule_id")
            schedule_name = schedule.get("name", f"Schedule {schedule_id}")
            
            # Truncate name if too long
            name_text = schedule_name[:25] if len(schedule_name) > 25 else schedule_name
            
            # Create row with 2 buttons
            row_buttons = [
                # Left button: Schedule name (does nothing when clicked)
                InlineKeyboardButton(
                    f"📅 {name_text}",
                    callback_data="do_nothing"  # This callback does nothing
                ),
                # Right button: Delete icon
                InlineKeyboardButton(
                    "🗑️ ᴅᴇʟᴇᴛᴇ",
                    callback_data=f"confirm_delete_{schedule_id}"
                )
            ]
            buttons.append(row_buttons)
    
    # Add refresh button at the end
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="list_schedules")])
    
    await callback_query.message.edit_text(
        result_msg,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Handler for the "do nothing" button
@Client.on_callback_query(filters.regex(r"^do_nothing$"))
async def do_nothing_handler(client, callback_query: CallbackQuery):
    # Just acknowledge the click without doing anything
    await callback_query.answer("ℹ️ Click the 🗑️ button to delete", show_alert=False)

# ============ COMMAND FOR LISTING SCHEDULES ============ #
@Client.on_message(filters.command(["listschedules", "schedules"]) & filters.private & admin_filter)
async def list_schedules_command(client, message: Message):
    # Create a simple list response with inline buttons
    schedules = await db.get_all_schedules()
    
    if not schedules:
        await message.reply("📋 <b>No schedules found.</b>")
        return
    
    # Get current IST time
    now_ist = datetime.now(IST)
    current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
    
    result_msg = f"<blockquote>📋 <b>All Schedules</b></blockquote>\n"
    result_msg += f"<i>Current Time: {current_time_str}</i>\n\n"
    
    # Show total count
    result_msg += f"<b>Total Schedules:</b> {len(schedules)}\n\n"
    
    # Show first few schedules as example
    for schedule in schedules[:3]:
        schedule_id = schedule.get("schedule_id")
        schedule_name = schedule.get("name", f"Schedule {schedule_id}")
        group = schedule.get("group", "0")
        times = ', '.join(schedule.get("schedule_times", []))[:25]
        
        result_msg += f"• <b>{schedule_name}</b> (Group {group})\n"
        result_msg += f"  Times: {times} IST\n"
    
    if len(schedules) > 3:
        result_msg += f"\n<i>...and {len(schedules) - 3} more schedules</i>\n\n"
    
    result_msg += "Click below to view and manage all schedules:"
    
    buttons = [
        [InlineKeyboardButton("📋 View & Manage All Schedules", callback_data="list_schedules")]
    ]
    
    await message.reply(
        result_msg,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ============ COMMAND FOR DELETING SCHEDULE BY ID ============ #
@Client.on_message(filters.command(["deleteschedule", "delschedule"]) & filters.private & admin_filter)
async def delete_schedule_command(client, message: Message):
    if len(message.command) < 2:
        await message.reply(
            "**❌ Please specify a schedule ID!**\n\n"
            "**Format:** `/deleteschedule 1234567890`\n\n"
            "**To get schedule IDs:**\n"
            "• Use `/schedules` to list all schedules\n"
            "• Or use the inline buttons in schedule list\n\n"
            "**Example:** `/deleteschedule 1234567890`"
        )
        return
    
    try:
        schedule_id = int(message.command[1])
    except ValueError:
        await message.reply("**❌ Invalid schedule ID!** Schedule ID must be a number.")
        return
    
    # Get schedule info
    schedule = await db.get_schedule(schedule_id)
    if not schedule:
        await message.reply(f"**❌ Schedule not found!**\n\nNo schedule with ID <code>{schedule_id}</code>")
        return
    
    schedule_name = schedule.get("name", f"Schedule {schedule_id}")
    group = schedule.get("group", "0")
    times = ', '.join(schedule.get("schedule_times", []))
    
    # Ask for confirmation
    confirm_msg = await message.reply(
        f"**⚠️ Confirm Schedule Deletion**\n\n"
        f"• <b>Schedule Name:</b> {schedule_name}\n"
        f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
        f"• <b>Group:</b> {group}\n"
        f"• <b>Times:</b> {times} IST\n\n"
        f"Are you sure you want to delete this schedule?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"cmd_delete_yes_{schedule_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cmd_delete_no")
            ]
        ])
    )

@Client.on_callback_query(filters.regex(r"^cmd_delete_yes_"))
async def cmd_delete_yes_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Deleting schedule...")
    
    schedule_id = int(callback_query.data.split("_")[3])
    
    # Get schedule info before deleting
    schedule = await db.get_schedule(schedule_id)
    
    # Delete schedule from database
    await db.delete_schedule(schedule_id)
    
    if schedule:
        schedule_name = schedule.get("name", f"Schedule {schedule_id}")
        await callback_query.message.edit_text(
            f"✅ <b>Schedule Deleted</b>\n\n"
            f"• <b>Schedule Name:</b> {schedule_name}\n"
            f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
            f"• <b>Group:</b> {schedule.get('group', '0')}\n\n"
            f"This schedule will no longer run."
        )
    else:
        await callback_query.message.edit_text(
            f"✅ <b>Schedule Deleted</b>\n\n"
            f"• <b>Schedule ID:</b> <code>{schedule_id}</code>\n\n"
            f"This schedule will no longer run."
        )
    
    # Log deletion
    try:
        now_ist = datetime.now(IST)
        current_time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")
        
        log_msg = (
            f"🗑 <blockquote><b>#ScheduleDeleted</b></blockquote>\n\n"
            f"👤 <b>Deleted By:</b> {callback_query.from_user.mention}\n"
            f"🕐 <b>Deleted At:</b> {current_time_str}\n"
            f"📌 <b>Schedule ID:</b> <code>{schedule_id}</code>\n"
            f"📝 <b>Via Command:</b> Yes\n"
        )
        
        await client.send_message(
            chat_id=LOG_CHANNEL,
            text=log_msg
        )
    except:
        pass

@Client.on_callback_query(filters.regex(r"^cmd_delete_no$"))
async def cmd_delete_no_handler(client, callback_query: CallbackQuery):
    await callback_query.answer("Deletion cancelled")
    await callback_query.message.edit_text("❌ Schedule deletion cancelled.")
