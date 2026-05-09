import emoji
import re
import unicodedata

from pyxavi import dd

class Text:

    @staticmethod
    def remove_emojis(text: str) -> str:
        return Text._get_emoji_regexp().sub(r'', text)

    @staticmethod
    def _get_emoji_regexp():
        # Sort emoji by length to make sure multi-character emojis are
        # matched first
        emojis = sorted(emoji.EMOJI_DATA, key=len, reverse=True)
        pattern = '(' + '|'.join(re.escape(u) for u in emojis) + ')'
        return re.compile(pattern)
    
    @staticmethod
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

    @staticmethod
    def replace_known_text(text: str, replacements: dict) -> str:
        '''
        Replaces known text patterns with their corresponding characters.
        '''
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    @staticmethod
    def remove_accents(text: str) -> str:
        '''
        Removes accents from characters in the text.
        '''
        nfkd_form = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in nfkd_form if not unicodedata.combining(c)])


class Code:

    CODE_BLOCK_TRIPLE_BACKTICKS = r'[`]{3}'

    @staticmethod
    def text_includes_code(text: str) -> bool:
        """
        Checks if the text of the response includes code snippets.
        This is a very naive implementation that checks for the presence of triple backticks.
        Returns:
            bool: True if the text includes code snippets, False otherwise.
        """
        return text is not None and re.search(Code.CODE_BLOCK_TRIPLE_BACKTICKS, text) is not None
    
    @staticmethod
    def extract_code_from_text(text: str) -> list[str]:
        """
        Extracts code snippets from the text of the response.
        It relies on the presence of triple backticks to identify code blocks, one per line.
        It can handle multiple code blocks in the same text, but it does not handle nested code blocks 
            or code blocks that are not properly closed.

        Returns:
            list[str]: The extracted code snippets, or None if no code snippets are found.
        """

        if text is None:
            return None
        
        outcome = []
        lines = text.split("\n")
        current_code_block_lines = []
        line_is_in_code_block = False
        for line in lines:

            # Check if this line includes triple backticks, which may indicate the start or end of a code block.
            if re.search(Code.CODE_BLOCK_TRIPLE_BACKTICKS, line) is not None:
                # toggle the flag
                line_is_in_code_block = not line_is_in_code_block

                # If there are 2 code blocks in consecutive lines without new line between the triple backticks, like:
                # ```
                # print("Hello World")
                # ```
                # ```
                # print("Hello again")
                # ```
                # we need to reset the current code block lines, as the naive code block extractor will consider that we are still in the same code block.
                if line_is_in_code_block and len(current_code_block_lines) > 0:
                    outcome.append("\n".join(current_code_block_lines))
                    current_code_block_lines = []

                # discard the actual line with the triple backticks, as it is not part of the code.
                continue
            
            if line_is_in_code_block:
                # The current line matches the ticks, append the line into the current code block lines
                current_code_block_lines.append(line)
            else:
                # The current line does not match the ticks:
                #   if we are currently accummulating a code block, dump it into the outcome and reset the current code block lines.
                if len(current_code_block_lines) > 0:
                    outcome.append("\n".join(current_code_block_lines))
                    current_code_block_lines = []
        
        # If we finished the loop and we are still accummulating a code block, dump it into the outcome.
        if len(current_code_block_lines) > 0:
            outcome.append("\n".join(current_code_block_lines))

        return outcome if len(outcome) > 0 else None
    
    @staticmethod
    def remove_all_code_blocks_from_text(text: str) -> str:
        """
        Removes code snippets from the text of the response.
        This is a very naive implementation that removes text between triple backticks.
        """
        outcome = []
        line_is_in_code_block = False
        for line in text.split("\n"):
            matches = re.search(Code.CODE_BLOCK_TRIPLE_BACKTICKS, line)
            if matches is not None:
                line_is_in_code_block = not line_is_in_code_block
                continue
            if not line_is_in_code_block:
                outcome.append(line)
        
        return "\n".join(outcome).strip()
    
    @staticmethod
    def remove_comment_lines_from_code(text: str) -> str:
        """
        Removes comment lines from the extracted code.
        This is a very naive implementation that removes lines starting with # or //.
        """
        if text is None:
            return None
        
        lines = text.split("\n")
        non_comment_lines = [line for line in lines if not line.strip().startswith("#") and not line.strip().startswith("//")]
        return "\n".join(non_comment_lines).strip()
    
    @staticmethod
    def remove_code_language_identifier(text: str) -> str:
        """
        Removes the language identifier from the code block if it exists.
        This is a very naive implementation that removes the first line if it does not contain code.
        """
        if text is None:
            return None
        
        outcome = []
        lines = text.split("\n")
        for line in lines:
            # I've seen some text with 2 code blocks, without new line between the triplebackticks, like:
            # ```python
            # print("Hello World")
            # ``````python
            # print("Hello again")
            # ````
            matches = re.finditer(Code.CODE_BLOCK_TRIPLE_BACKTICKS, line)
            new_line = []
            for match in matches:
                new_line = []
                substring_start = match.start()
                substring_end = match.end()
                new_line.append(line[substring_start:substring_end])
                outcome.append("\n".join(new_line))
            if len(new_line) == 0:
                outcome.append(line)
        
        return "\n".join(outcome).strip()