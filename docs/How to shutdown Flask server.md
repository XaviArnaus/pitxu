# How to shutdown Flask server

You can shut down a Flask server using several methods, depending on whether you are in a development environment or need a programmatic solution.

### In Development (Local Server)

*   **Ctrl+C**: The most common and straightforward way to shut down a Flask development server running in your terminal is to press `Ctrl+C`. This sends an interrupt signal (SIGINT) to the process, causing it to terminate.

### Programmatic Shutdown

For more controlled or automated shutdowns, especially when you need to stop the server from within your application or another script, you can implement specific endpoints or manage the server process directly.

1.  **Using a Shutdown Endpoint (for Werkzeug development server):**
    While `werkzeug.server.shutdown` is deprecated, a common pattern for earlier versions and simple cases involves creating an endpoint that triggers the server's shutdown function. This typically involves accessing the `werkzeug.server.shutdown` function from `request.environ`.

    ```python
    from flask import Flask, request, jsonify
    import os
    import signal

    app = Flask(__name__)

    def shutdown_server():
        # This approach targets the Werkzeug development server
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

    @app.route('/shutdown', methods=['GET'])
    def shutdown():
        shutdown_server()
        return 'Server shutting down...'

    # A more robust programmatic shutdown using os.kill
    @app.route('/stopServer', methods=['GET'])
    def stopServer():
        os.kill(os.getpid(), signal.SIGINT)
        return jsonify({ "success": True, "message": "Server is shutting down..." })

    if __name__ == '__main__':
        app.run(debug=True)
    ```
    To shut down the server, you would navigate to `http://127.0.0.1:5000/shutdown` or `http://127.0.0.1:5000/stopServer` in your browser or send an HTTP GET request to it.

2.  **Managing with `multiprocessing`:**
    For scenarios where you need to run the Flask app as a separate process and control its lifecycle, Python's `multiprocessing` module is effective. You can start the Flask app in a separate process and then terminate that process when needed.

    ```python
    from flask import Flask
    from multiprocessing import Process
    import time

    app = Flask(__name__)

    @app.route('/')
    def hello():
        return "Hello, Flask!"

    def run_flask_app():
        app.run(port=5000)

    if __name__ == '__main__':
        server_process = Process(target=run_flask_app)
        server_process.start()
        print("Flask server started in a separate process.")

        # Let the server run for some time (e.g., 5 seconds)
        time.sleep(5)

        # Terminate the server process
        server_process.terminate()
        server_process.join()
        print("Flask server shut down.")
    ```

3.  **Sending a Signal to the Process:**
    You can send a signal directly to the Flask application's process ID (PID) to terminate it. `os.kill(pid, signal.SIGINT)` sends an interrupt signal, similar to `Ctrl+C`.

    ```python
    import os
    import signal
    import time

    # Assuming you know the PID of your Flask application
    # For demonstration, let's assume a hypothetical PID
    # In a real scenario, you'd get the PID through other means
    # e.g., storing it when the server starts, or finding it with system tools.
    flask_app_pid = 12345 # Replace with the actual PID of your Flask server

    try:
        os.kill(flask_app_pid, signal.SIGINT)
        print(f"Sent SIGINT to process {flask_app_pid}")
    except ProcessLookupError:
        print(f"Process with PID {flask_app_pid} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
    ```

### Direct Process Termination (Command Line)

If you need to stop a Flask server from the command line and you don't have a programmatic shutdown endpoint, you can find and kill its process:

*   **Using `pgrep` and `kill` (Linux/macOS):**
    1.  Find the process ID (PID) of your Flask application:
        ```bash
        pgrep -f "flask run"
        # or if running with python -m flask run:
        # pgrep -f "python -m flask run"
        # or if running a specific script:
        # pgrep -f "python your_app.py"
        ```
        This command will list the PIDs of processes matching the pattern.
    2.  Kill the process using its PID:
        ```bash
        kill -9 <PROCESSID>
        ```
        Replace `<PROCESSID>` with the actual PID obtained from the previous step. The `-9` flag sends a SIGKILL signal, which forcefully terminates the process.