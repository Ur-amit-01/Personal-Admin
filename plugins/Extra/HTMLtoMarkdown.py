import re
from typing import Dict, Tuple
import random
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import ADMIN
from plugins.Post.admin_panel import admin_filter

class TelegramHTMLConverter:
    """
    Converts Telegram Markdown to HTML format compatible with Telegram's limited HTML support.
    This implementation is optimized for Telegram's specific requirements.
    """
    
    @staticmethod
    def convert_html_chars(text: str) -> str:
        """Converts HTML reserved symbols to their respective character references."""
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text
    
    @staticmethod
    def split_by_tag(text: str, md_tag: str, html_tag: str) -> str:
        """Splits the text by markdown tag and replaces it with the specified HTML tag."""
        # Escape special regex characters
        escaped_md_tag = re.escape(md_tag)
        # Pattern to match the tag (negative lookbehind/lookahead to avoid word characters)
        pattern = re.compile(fr'(?<!\w){escaped_md_tag}(.*?){escaped_md_tag}(?!\w)', re.DOTALL)
        
        # Special handling for the tg-spoiler tag
        if html_tag == 'span class="tg-spoiler"':
            return pattern.sub(r'<span class="tg-spoiler">\1</span>', text)
        
        return pattern.sub(fr'<{html_tag}>\1</{html_tag}>', text)
    
    @staticmethod
    def ensure_closing_delimiters(text: str) -> str:
        """Ensures code blocks have proper closing backticks."""
        # For triple backticks
        if text.count('```') % 2 != 0:
            text += '```'
        # For single backticks
        if text.count('`') % 2 != 0:
            text += '`'
        return text
    
    @staticmethod
    def extract_and_convert_code_blocks(text: str) -> Tuple[str, Dict[str, str]]:
        """Extracts code blocks and converts them to HTML format."""
        text = TelegramHTMLConverter.ensure_closing_delimiters(text)
        placeholders = []
        code_blocks = {}
        
        # Pattern to match code blocks with optional language
        pattern = re.compile(r'```(\w*)?\n?(.*?)```', re.DOTALL)
        modified_text = text
        idx = 0
        
        for match in pattern.finditer(text):
            language = match.group(1) or ''
            code_content = match.group(2)
            
            # Escape HTML entities in code content
            escaped_content = (code_content
                             .replace('&', '&amp;')
                             .replace('<', '&lt;')
                             .replace('>', '&gt;'))
            
            placeholder = f'CODEBLOCKPLACEHOLDER{idx}'
            placeholders.append(placeholder)
            
            if not language:
                html_code_block = f'<pre><code>{escaped_content}</code></pre>'
            else:
                html_code_block = f'<pre><code class="language-{language}">{escaped_content}</code></pre>'
            
            code_blocks[placeholder] = html_code_block
            modified_text = modified_text.replace(match.group(0), placeholder, 1)
            idx += 1
        
        return modified_text, code_blocks
    
    @staticmethod
    def extract_inline_code_snippets(text: str) -> Tuple[str, Dict[str, str]]:
        """Extracts inline code snippets."""
        placeholders = []
        code_snippets = {}
        pattern = re.compile(r'`([^`]+)`')
        modified_text = text
        idx = 0
        
        for match in pattern.finditer(text):
            snippet = match.group(1)
            placeholder = f'INLINECODEPLACEHOLDER{idx}'
            placeholders.append(placeholder)
            code_snippets[placeholder] = snippet
            modified_text = modified_text.replace(match.group(0), placeholder, 1)
            idx += 1
        
        return modified_text, code_snippets
    
    @staticmethod
    def combine_blockquotes(text: str) -> str:
        """Combines multiline blockquotes into single HTML blockquotes."""
        lines = text.split('\n')
        combined_lines = []
        blockquote_lines = []
        in_blockquote = False
        is_expandable = False
        
        for line in lines:
            if line.startswith('**>'):
                in_blockquote = True
                is_expandable = True
                blockquote_lines.append(line[3:].strip())
            elif line.startswith('>'):
                if not in_blockquote:
                    in_blockquote = True
                    is_expandable = False
                blockquote_lines.append(line[1:].strip())
            else:
                if in_blockquote:
                    if is_expandable:
                        combined_lines.append(
                            '<blockquote expandable>' + 
                            '\n'.join(blockquote_lines) + 
                            '</blockquote>'
                        )
                    else:
                        combined_lines.append(
                            '<blockquote>' + 
                            '\n'.join(blockquote_lines) + 
                            '</blockquote>'
                        )
                    blockquote_lines = []
                    in_blockquote = False
                    is_expandable = False
                combined_lines.append(line)
        
        # Handle blockquote at end of text
        if in_blockquote:
            if is_expandable:
                combined_lines.append(
                    '<blockquote expandable>' + 
                    '\n'.join(blockquote_lines) + 
                    '</blockquote>'
                )
            else:
                combined_lines.append(
                    '<blockquote>' + 
                    '\n'.join(blockquote_lines) + 
                    '</blockquote>'
                )
        
        return '\n'.join(combined_lines)
    
    @staticmethod
    def fix_asterisk_equations(text: str) -> str:
        """Replaces '*' in numeric expressions with '×' to avoid italic formatting."""
        pattern = re.compile(r'(\d+)\s*\*\s*(\d+)')
        return pattern.sub(r'\1×\2', text)
    
    @staticmethod
    def remove_escaping(text: str) -> str:
        """Removes escaping from Telegram-specific HTML tags."""
        # Blockquotes
        text = (text
                .replace('&lt;blockquote&gt;', '<blockquote>')
                .replace('&lt;/blockquote&gt;', '</blockquote>')
                .replace('&lt;blockquote expandable&gt;', '<blockquote expandable>'))
        
        # Spoiler tags
        text = (text
                .replace('&lt;span class="tg-spoiler"&gt;', '<span class="tg-spoiler">')
                .replace('&lt;/span&gt;', '</span>'))
        
        return text
    
    @staticmethod
    def telegram_format(text: str) -> str:
        """Main function to convert Markdown to Telegram HTML format."""
        # Step 1: Combine blockquotes
        text = TelegramHTMLConverter.combine_blockquotes(text)
        
        # Step 2: Extract and convert code blocks
        text, code_blocks = TelegramHTMLConverter.extract_and_convert_code_blocks(text)
        
        # Step 3: Extract inline code snippets
        text, inline_snippets = TelegramHTMLConverter.extract_inline_code_snippets(text)
        
        # Step 4: Convert HTML reserved characters
        processed_text = TelegramHTMLConverter.convert_html_chars(text)
        
        # Step 5: Convert headings (H1-H6 to bold)
        processed_text = re.sub(r'^(#{1,6})\s+(.+)$', r'<b>\2</b>', processed_text, flags=re.MULTILINE)
        
        # Step 6: Convert unordered lists
        processed_text = re.sub(r'^(\s*)[\-\*]\s+(.+)$', r'\1• \2', processed_text, flags=re.MULTILINE)
        
        # Step 7: Nested Bold and Italic
        processed_text = processed_text.replace('***', '<b><i>').replace('***', '</i></b>')
        processed_text = processed_text.replace('___', '<u><i>').replace('___', '</i></u>')
        
        # Step 8: Process other formatting
        processed_text = TelegramHTMLConverter.split_by_tag(processed_text, '**', 'b')
        processed_text = TelegramHTMLConverter.split_by_tag(processed_text, '__', 'u')
        processed_text = TelegramHTMLConverter.split_by_tag(processed_text, '~~', 's')
        processed_text = TelegramHTMLConverter.split_by_tag(processed_text, '||', 'span class="tg-spoiler"')
        
        # Step 9: Single asterisk italic (careful with equations)
        processed_text = TelegramHTMLConverter.fix_asterisk_equations(processed_text)
        italic_pattern = re.compile(r'(?<![A-Za-z0-9])\*(?=[^\s])(.*?)(?<!\s)\*(?![A-Za-z0-9])', re.DOTALL)
        processed_text = italic_pattern.sub(r'<i>\1</i>', processed_text)
        
        # Step 10: Single underscore italic
        processed_text = TelegramHTMLConverter.split_by_tag(processed_text, '_', 'i')
        
        # Step 11: Remove storage links
        processed_text = re.sub(r'【[^】]+】', '', processed_text)
        
        # Step 12: Convert links
        link_pattern = re.compile(r'(?:!?)\[((?:[^\[\]]|\[.*?\])*)\]\(([^)]+)\)')
        processed_text = link_pattern.sub(r'<a href="\2">\1</a>', processed_text)
        
        # Step 13: Reinsert inline code snippets
        for placeholder, snippet in inline_snippets.items():
            escaped_snippet = (snippet
                             .replace('&', '&amp;')
                             .replace('<', '&lt;')
                             .replace('>', '&gt;'))
            processed_text = processed_text.replace(placeholder, f'<code>{escaped_snippet}</code>')
        
        # Step 14: Reinsert code blocks
        for placeholder, html_block in code_blocks.items():
            processed_text = processed_text.replace(placeholder, html_block)
        
        # Step 15: Remove escaping from Telegram tags
        processed_text = TelegramHTMLConverter.remove_escaping(processed_text)
        
        # Step 16: Clean up multiple consecutive newlines
        processed_text = re.sub(r'\n{3,}', '\n\n', processed_text)
        
        return processed_text.strip()


# Add REACTIONS list if not already defined
REACTIONS = ["👍", "👌", "🔥", "✨", "💯", "⭐", "🌟", "🚀"]

@Client.on_message(filters.command("html") & filters.private)
async def convert_to_html(client, message: Message):
    """
    Converts Telegram Markdown to HTML formatting.
    Usage: Reply to a message with /html or use /html [text]
    """
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except:
        pass
    
    # Check if user replied to a message
    if message.reply_to_message:
        # Get text from replied message
        if message.reply_to_message.text:
            text_to_convert = message.reply_to_message.text
        elif message.reply_to_message.caption:
            text_to_convert = message.reply_to_message.caption
        else:
            await message.reply("❌ The replied message doesn't contain any text to convert.")
            return
    elif len(message.command) > 1:
        # Get text from command arguments
        text_to_convert = " ".join(message.command[1:])
    else:
        await message.reply(
            "**Usage:**\n"
            "1. Reply to a message with `/html`\n"
            "2. Or type `/html [your markdown text]`\n\n"
            "**Example:** `/html **bold** and _italic_ text`"
        )
        return
    
    # Show processing message
    processing_msg = await message.reply(
        f"🔄 **Converting Markdown to HTML...**\n\n"
        f"📝 **Original length:** {len(text_to_convert)} characters\n"
        f"⏳ *Processing...*"
    )
    
    try:
        # Convert the text
        converted_html = TelegramHTMLConverter.telegram_format(text_to_convert)
        
        # Prepare the response
        response = (
            f"✅ **Successfully Converted**\n\n"
            f"📊 **Stats:**\n"
            f"• Original: {len(text_to_convert)} chars\n"
            f"• Converted: {len(converted_html)} chars\n\n"
            f"📋 **HTML Output:**\n"
            f"```html\n{converted_html[:1900]}```"
        )
        
        # If HTML is too long, send it as a separate message
        if len(converted_html) > 1900:
            await message.reply(
                f"📋 **HTML Output (Full):**\n\n"
                f"```html\n{converted_html}```"
            )
        
        await processing_msg.edit_text(response)
        
    except Exception as e:
        error_msg = (
            f"❌ **Conversion Failed**\n\n"
            f"**Error:** `{str(e)}`\n\n"
            f"**Original Text:**\n"
            f"```\n{text_to_convert[:500]}```"
        )
        await processing_msg.edit_text(error_msg)
