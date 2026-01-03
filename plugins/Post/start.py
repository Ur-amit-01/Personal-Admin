from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, BotCommand
from config import *
from plugins.helper.db import db
import random
from plugins.Post.admin_panel import admin_filter
from html.parser import HTMLParser
import re

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

#=====================================================================================


# Add to commands list in /set command
#BotCommand("html2md", "📝 Convert HTML to Markdown")

# HTML to Markdown converter class
class HTMLToMarkdownConverter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.current_tag = None
        self.link_url = None
        self.link_text = []
        
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
        
        if tag == 'a':
            # Extract href from anchor tags
            for attr, value in attrs:
                if attr == 'href':
                    self.link_url = value
                    break
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Add newline before headings
            self.result.append('\n')
        elif tag == 'br':
            self.result.append('\n')
        elif tag == 'hr':
            self.result.append('\n---\n')
        elif tag == 'li':
            self.result.append('- ')
            
    def handle_endtag(self, tag):
        tag = tag.lower()
        
        if tag == 'a' and self.link_url:
            # Complete link in markdown format
            link_text = ''.join(self.link_text).strip()
            if link_text and self.link_url:
                self.result.append(f'[{link_text}]({self.link_url})')
            self.link_url = None
            self.link_text = []
        elif tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.result.append('\n\n')
        elif tag in ['p', 'div']:
            self.result.append('\n\n')
        elif tag == 'li':
            self.result.append('\n')
            
        self.current_tag = None
        
    def handle_data(self, data):
        if self.current_tag == 'a':
            self.link_text.append(data)
        else:
            # Apply markdown formatting based on tag
            if self.current_tag in ['b', 'strong']:
                self.result.append(f'**{data}**')
            elif self.current_tag in ['i', 'em']:
                self.result.append(f'*{data}*')
            elif self.current_tag in ['code']:
                self.result.append(f'`{data}`')
            elif self.current_tag in ['h1']:
                self.result.append(f'# {data}')
            elif self.current_tag in ['h2']:
                self.result.append(f'## {data}')
            elif self.current_tag in ['h3']:
                self.result.append(f'### {data}')
            elif self.current_tag in ['h4', 'h5', 'h6']:
                self.result.append(f'#### {data}')
            else:
                self.result.append(data)

def html_to_markdown(html_text):
    """Convert HTML to Markdown"""
    # Clean common HTML issues
    html_text = re.sub(r'</b><b>', '', html_text)
    html_text = re.sub(r'### href=', '', html_text)
    html_text = re.sub(r'<b>\s*</b>', '', html_text)
    
    # Create parser and parse
    parser = HTMLToMarkdownConverter()
    parser.feed(html_text)
    
    # Get result and clean up
    markdown = ''.join(parser.result)
    
    # Post-processing
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)  # Remove excessive newlines
    markdown = markdown.strip()
    
    return markdown

# Command handler
@Client.on_message(filters.private & filters.command("html2md"))
async def html_to_markdown_command(client, message: Message):
    # Check if replying to a message
    if message.reply_to_message and message.reply_to_message.text:
        html_content = message.reply_to_message.text
    else:
        # Check if command has arguments
        if len(message.command) > 1:
            html_content = ' '.join(message.command[1:])
        else:
            await message.reply_text(
                "**Usage:**\n"
                "• Reply to an HTML message with `/html2md`\n"
                "• Or send `/html2md <your_html_here>`\n\n"
                "**Example:**\n"
                '/html2md <b>Hello</b> <a href="https://example.com">Click</a>'
            )
            return
    
    try:
        # Convert HTML to Markdown
        markdown_result = html_to_markdown(html_content)
        
        # Prepare response
        if len(markdown_result) > 4000:
            # Send as file if too long
            await message.reply_document(
                document=("converted.md", markdown_result.encode()),
                caption="✅ HTML converted to Markdown (sent as file due to length)"
            )
        else:
            # Send as code block
            response = f"**✅ Converted HTML to Markdown:**\n\nmarkdown\n{markdown_result}\n"
            await message.reply_text(response, disable_web_page_preview=True)
            
    except Exception as e:
        await message.reply_text(f"❌ Error converting HTML:\n`{str(e)}`")
