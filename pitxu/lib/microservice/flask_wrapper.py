from werkzeug import serving
from flask import Flask
from threading import Thread

class FlaskWrapper(Thread):

    server: serving.ThreadedWSGIServer
    ctx: Flask.app_context

    def __init__(self, app, host: str, port: int, debug: bool = False):

        super().__init__()
        
        self.server = serving.make_server(
            host,
            port,
            app,
            threaded=True,
            passthrough_errors=True,
        )
        
        self.ctx = app.app_context() # Needed for Flask context within the thread
        self.daemon = True # Allows the thread to exit when the main program exits
    
    def run(self):
        self.ctx.push() # Push the application context
        self.server.serve_forever()

    
    def shutdown(self):
        self.server.shutdown()
    
    def add_endpoint(self, rule, endpoint=None, view_func=None, **options):
        self.server.service_actions .add_url_rule(rule, endpoint=endpoint, view_func=view_func, **options)