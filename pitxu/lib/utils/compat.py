import queue

# queue.ShutDown only exists on Python 3.13+. On older versions use a placeholder
# that nothing raises, so `except QueueShutDown` stays valid everywhere.
QueueShutDown = getattr(queue, "ShutDown", None) or type("QueueShutDown", (Exception,), {})