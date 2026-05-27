import urllib.request

from pyxavi import Config, Dictionary
from pitxu.lib.abstract.pyxavi import PyXavi

import json

class Github(PyXavi):

    # ATM it only has access to PRs
    GITHUB_TOKEN: str = None

    def __init__(self, config: Config = None, params: Dictionary = None, **kwargs):
        super(Github, self).init_pyxavi(config=config, params=params)

        self.GITHUB_TOKEN = self._xparams.get("github_token", None)

    def get_files_involved_in_pr(self, pr_url: str) -> list[str]:
        """
        Gets the list of files involved in a PR, given the PR URL.

        It uses the GitHub API to get the list of files involved in the PR.

        Args:
            pr_url (str): The URL of the PR.

        Returns:
            list[str]: The list of files involved in the PR.
        """
        if self.GITHUB_TOKEN is None:
            self._xlog.error("🛑 GITHUB_TOKEN is not set. Please set it in the .env file.")
            return []

        # Extract owner, repo and pr number from the URL
        try:
            parts = pr_url.split("/")
            owner = parts[3]
            repo = parts[4]
            pr_number = parts[6]
        except Exception as e:
            self._xlog.error(f"Error parsing PR URL: {e}")
            return []

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        try:
            request = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(request) as response:
                data = response.read()
                
                files_info = json.loads(data)
                files_data = []
                for file_info in files_info:
                    self._log_debug(f"File in PR: {file_info['filename']}")
                    file_data = {
                        "name": file_info["filename"],
                        "status": file_info["status"],
                        "raw_url": file_info["raw_url"],
                        "contents_url": file_info["contents_url"],
                    }
                    files_data.append(file_data)
                return files_data
        except Exception as e:
            self._xlog.error(f"Error fetching PR files: {e}")
            return []