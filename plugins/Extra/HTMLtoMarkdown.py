from pyrogram import Client, filters
from pyrogram.types import Message
import html

@Client.on_message(filters.command("html") & filters.private)
async def html_command(client: Client, message: Message):
    """Convert replied message to HTML formatting."""
    
    if not message.reply_to_message:
        await message.reply("Reply to a message with /html")
        return
    
    replied_msg = message.reply_to_message
    
    if not replied_msg.text and not replied_msg.caption:
        await message.reply("No text to convert")
        return
    
    content = replied_msg.text or replied_msg.caption or ""
    
    if not replied_msg.entities and not replied_msg.caption_entities:
        html_content = html.escape(content)
        await message.reply(f"```html\n{html_content}\n```")
        return
    
    entities = replied_msg.entities or replied_msg.caption_entities or []
    text = content
    
    for entity in sorted(entities, key=lambda x: x.offset, reverse=True):
        offset = entity.offset
        length = entity.length
        
        if entity.type == "bold":
            tag = "b"
        elif entity.type == "italic":
            tag = "i"
        elif entity.type == "underline":
            tag = "u"
        elif entity.type == "strikethrough":
            tag = "s"
        elif entity.type == "code":
            tag = "code"
        elif entity.type == "pre":
            tag = "pre"
        elif entity.type == "text_link":
            url = entity.url
            tag = f'a href="{html.escape(url)}"'
        elif entity.type == "spoiler":
            tag = 'span class="tg-spoiler"'
        else:
            continue
        
        start_tag = f"<{tag}>"
        end_tag = f"</{tag.split()[0].split('=')[0]}>"
        text = text[:offset] + start_tag + text[offset:offset+length] + end_tag + text[offset+length:]
    
    await message.reply(f"```html\n{text}\n```")
