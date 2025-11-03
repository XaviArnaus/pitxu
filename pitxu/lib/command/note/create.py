from pyxavi import Config, Dictionary
from pitxu.lib.abstract import Xprocess

import logging
import requests
import os

class CreateNote(Xprocess):

    def initialize(self):
        '''
        This is called from from __init__() when instantiated (can be avoided) or from 
        outside via QueueItemAction.INITIALIZE to init itself anything, 
        it won't be triggered in every run(). 
        Most likely you want to initiate here the models within the Process, avoiding
        issues with session serialisation (I look at you, PiperSession)
        '''

        super(Xprocess, self).__init__()
    
    def do(self, config: Config, logger: logging):
        '''
        This is what you want to implement in your child class as the actual work.
        Called from run() with the initialised basic framework.
        '''

        url = 'https://magatzem.arnaus.net:5001/webapi/entry.cgi'

        # data = {
        # 'api': 'SYNO.FileStation.Download',
        # 'version': '2',
        # 'method': 'upload',
        # 'path': config.get("storage.synology.path") + "/tmp/synology_note.md",
        # 'create_parents': 'true',
        # 'overwrite': 'true',
        # }
        # files = {'file': (open('123.txt', 'rb'))}

        # params = {
        #     '_sid': session_id,
        # }
        # response = requests.post(url, params=params, data=data, files=files)
        # print(response.json())

        with requests.Session() as session:

            # Authenticate
            data = {
                'api': 'SYNO.API.Auth',
                'version': '2',
                'method': 'method=login',
                'account': os.getenv("SYNOLOGY_USER", None),
                'passwd': os.getenv("SYNOLOGY_PASSWORD", None),
                'session': "Pepito"
            }
            r = session.get(url, data=data)

            if r.status_code == 200:
                # Download the file of the note
                data = {
                    'api': 'SYNO.FileStation.Download',
                    'version': '2',
                    'method': 'download',
                    'path': config.get("storage.synology.path") + "/tmp/synology_note.md",
                    'dest_path': config.get("storage.tmp") + "/synology_note.md",
                }

                # r = session.post(url, data=data, files=files)
                r = session.post(url, data=data)

                print(r.json)
            
            else:
                logger.error("Could not authenticate: " + r.content)
    
    def finish(self):
        '''
        This is called from from run() via KeyboardInterrupt or from outside via 
        QueueItemAction.FINISH to finish gracefully whatever we have open.
        Do not try to terminate the process from inside itself.
        '''
        pass

    @staticmethod
    def generate_gemini_function():
        # https://ai.google.dev/gemini-api/docs/function-calling?example=meeting
        return {
            "name": "create_note",
            "description": "Creates a note file",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the note",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date of the meeting (e.g., '2024-07-29')",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time of the meeting (e.g., '15:00')",
                    },
                    "body": {
                        "type": "string",
                        "description": "The body of the note",
                    },
                },
                "required": ["title", "body"],
            },
        }