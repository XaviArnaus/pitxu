from pyxavi import Config, Logger
from pitxu.lib.utils.config_loader import ConfigLoader
from pitxu.lib.utils.api_request import ApiRequest

class WorldWikipedia:

    URL = f"https://%s.wikipedia.org/api/rest_v1/page/summary/%s"

    @staticmethod
    def get_summary_from_wikipedia_by_term(term: str) -> str:
        '''
        Gets the summary from Wikipedia for a specific term.

        Returns:
            The summary in plain text format.
        '''
        config: Config = ConfigLoader.load_config_files()
        logger = Logger(config=config, base_path="").get_logger()

        # These are the languages we support towards the ones supported by Wikipedia
        switch = {
            "en-us": "en",
            "es": "es",
            "ca": "ca",
            "de": "de",
        }
        lang = switch.get(config.get("app.default_language"), "en")

        logger.debug(f"Getting summary for language {lang} from Wikipedia for term: {term}")

        url = WorldWikipedia.URL % (lang, term)
        response = ApiRequest.do(url)
        if response and 'extract' in response:
            return response['extract']
        return "No summary available."