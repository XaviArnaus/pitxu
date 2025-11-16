import emoji
import re

class Text:

    def remove_emojis(text: str) -> str:
        return Text._get_emoji_regexp().sub(r'', text)

    def _get_emoji_regexp():
        # Sort emoji by length to make sure multi-character emojis are
        # matched first
        emojis = sorted(emoji.EMOJI_DATA, key=len, reverse=True)
        pattern = '(' + '|'.join(re.escape(u) for u in emojis) + ')'
        return re.compile(pattern)
    
    def remove_markdown(text:str) -> str:
        '''
        Removes basic markdown syntax from text.
        '''
        # Remove headings
        text = re.sub(r'#+ ', '', text)
        # Remove bold and italics
        text = re.sub(r'\*\*|__|\*|_', '', text)
        # Remove inline code
        text = re.sub(r'`', '', text)
        # Remove links but keep the link text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove images
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', r'\1', text)
        return text

    def replace_known_text(text: str, replacements: dict) -> str:
        '''
        Replaces known text patterns with their corresponding characters.
        '''
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text