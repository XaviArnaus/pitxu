import emoji
import re
import unicodedata

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
        This is a very naive implementation that extracts text between triple backticks.
        Returns:
            list[str]: The extracted code snippets, or None if no code snippets are found.
        """

        outcome = []
        while text is not None and Code.text_includes_code(text):
        
            # Naively extract code between triple backticks
            parts = re.split(Code.CODE_BLOCK_TRIPLE_BACKTICKS, text)
            if len(parts) < 3:
                return None
            
            # We take the first one. next iterations will care about the subsequent ones.
            code_block = parts[1].strip()

            # Keep track of the very first part
            part_0 = parts[0]
            # Remove it from the list of the parts
            del parts[0]
            # Now remove the code part to avoid extracting it again in the next iteration.
            # Note that it became the first part.
            del parts[0]
            # Reconstruct the text without the extracted code and the first part.
            # Note that we need to join them using the triple backticks again.
            text = part_0 + Code.CODE_BLOCK_TRIPLE_BACKTICKS.join(parts)

            # Finally append the cleaned code block to the outcome.
            outcome.append(code_block)
        
        return outcome if outcome else None
    
    @staticmethod
    def remove_all_code_blocks_from_text(text: str) -> str:
        """
        Removes code snippets from the text of the response.
        This is a very naive implementation that removes text between triple backticks.
        """
        outcome = []
        while text is not None and Code.text_includes_code(text):
        
            # Naively extract code between triple backticks
            parts = re.split(Code.CODE_BLOCK_TRIPLE_BACKTICKS, text)
            if len(parts) < 3:
                return None
            
            # We take the first one. next iterations will care about the subsequent ones.
            outcome.append(parts[1].strip())
            # Keep track of the very first part
            part_0 = parts[0]
            # Remove it from the list of the parts
            del parts[0]
            # Now remove the code part to avoid extracting it again in the next iteration.
            # Note that it became the first part.
            del parts[0]
            # Reconstruct the text without the extracted code and the first part.
            # Note that we need to join them using the triple backticks again.
            text = part_0 + Code.CODE_BLOCK_TRIPLE_BACKTICKS.join(parts)
        
        return text
    
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
            if matches:
                new_line = []
                for match in matches:
                    substring_start = match.start()
                    substring_end = match.end()
                    new_line.append(line[substring_start:substring_end])
                joiner = "\n" if len(new_line) > 1 else ""
                outcome.append(joiner.join(new_line))
            else:   
                outcome.append(line)
        
        return "\n".join(outcome).strip()