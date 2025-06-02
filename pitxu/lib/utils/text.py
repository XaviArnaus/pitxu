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