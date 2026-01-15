from pyxavi import Config, Dictionary

from pitxu.lib.abstract.pyxavi import PyXavi
from pitxu.lib.abstract.command import Command


class SystemLanguage(PyXavi, Command):

    def __init__(self, config: Config = None, params: Dictionary = None):
        super(SystemLanguage, self).init_pyxavi(config=config, params=params)

    def change_system_language(self, new_language: str) -> bool | str:
        '''
        Change the system language to the specified new language.

        Returns:
            bool | str: Returns the new language code if the language was changed successfully, False otherwise.
        '''
        try:
            self._xlog.info(f"Changing system language to: {new_language}")
            new_language_code = self._map_language_spoken_to_code(language_spoken=new_language)
            if new_language_code is None:
                self._xlog.error(f"🛑 Could not map spoken language '{new_language}' to a valid language code.")
                return False
            
            valid_languages = self._xconfig.get("app.supported_languages", [])
            if new_language_code not in valid_languages:
                self._xlog.error(f"🛑 Requested language '{new_language_code}' is not in the supported languages {valid_languages}")
                return False
            
            return new_language_code
        except Exception as e:
            self._xlog.error(f"Error changing system language: {e}")
            return False
    
    def _map_language_spoken_to_code(self, language_spoken: str) -> str:
        '''
        Map the language spoken to the language code used in the system.

        Args:
            language_spoken: The language spoken by the user.

        Returns:
            The language code used in the system.
        '''
        original_language_map = self._xconfig.get(f"language.languages_per_language", {})
        language_map = {}
        for _, lang_map in original_language_map.items():
            for lang_code, map in lang_map.items():
                if lang_code not in language_map:
                    language_map[lang_code] = []
                if isinstance(map, list):
                    language_map[lang_code].extend(map)
                else:
                    language_map[lang_code].append(map)

        also_language_codes = self._xconfig.get(f"language.language_codes_per_language", {})
        for lang_code, map in also_language_codes.items():
            if lang_code not in language_map:
                language_map[lang_code] = []
            if isinstance(map, list):
                language_map[lang_code].extend(map)
            else:
                language_map[lang_code].append(map)

        language_code = None
        for code, spoken in language_map.items():
            if isinstance(spoken, list):
                if language_spoken.lower() in [s.lower() for s in spoken]:
                    language_code = code
                    break
            else:
                if language_spoken.lower() == spoken.lower():
                    language_code = code
                    break
        return language_code

    def get_tool_definition(self) -> list[callable]:
        """
        Return the methods of the class that will be used as tools by the chatbot.

        It is used by ChatbotSessionManager to register the tools and link functions with callbacks.
        """
        return [self.change_system_language]
    
    def get_callback_by_given_function_name(self, function_name: str) -> callable:
        """
        Get the callback function for a given function name.

        It expects the function_name because a class may provide multiple functions as tools.

        Args:
            function_name: The name of the function to get the callback for.
        """
        # if function_name == "change_system_language":
        #     return self.callback_show_language_change
        return self.default_empty_callback
