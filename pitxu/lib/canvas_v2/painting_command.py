# TODO: Iterate this approach. As long as we need to do something like:
#     command=ForegroundCommand(ForegroundCommand.ARBITRARY_TEXT_ICON),
#   it looks like we're doing something wrong.

class PaintingCommand:
    """
    Base class for painting commands.
    Should be never instantiated, but inherited by specific command classes for foreground and background painting.
    Can be referenced for variable typing.
    """

    # These commands are common, regardless if they are for foreground, background or overall painting.
    # Could be also that they actually do nothing... but that's another issue.
    CLEAR: str = "CLEAR"

    available_commands: list = [CLEAR]
    command: str = None

    def __init__(self, command: str, available_commands: list):
        self.available_commands.extend(available_commands)
        if command not in self.available_commands:
            raise ValueError(f"Invalid command: {command}. Available commands are: {self.available_commands}.")
        self.command = command
    
    def get(self):
        return self.command
    
    def is_valid(self):
        return self.command in self.available_commands
    
    def matches(self, command: str):
        return self.command == command
    
    def included_in(self, commands: list):
        if isinstance(commands, list) and len(commands) == 0:
            return False
        if not isinstance(commands, list) and isinstance(commands, str):
            commands = [commands]
        return self.command in commands

class OverallCommand(PaintingCommand):
    """
    Commands related to an overall (full screen) painting.
    """

    CODE_BLOCK: str = "CODE_BLOCK"
    TEXT_BLOCK: str = "TEXT_BLOCK"

    def __init__(self, command: str):
        available_commands = [
            self.CODE_BLOCK,
            self.TEXT_BLOCK,
        ]
        super(OverallCommand, self).__init__(command, available_commands)

class ForegroundCommand(PaintingCommand):
    """
    Commands related to foreground painting.
    They are meant to be used in the (currently) "top-right" area of the screen, but they can be used in other areas as well.
    """

    STARTUP: str = "STARTUP"
    STARTUP_WITH_PHASE: str = "STARTUP_WITH_PHASE"
    ARBITRARY_TEXT: str = "ARBITRARY_TEXT"
    ARBITRARY_TEXT_ICON: str = "ARBITRARY_TEXT_ICON"
    ARBITRARY_ICON: str = "ARBITRARY_ICON"

    def __init__(self, command: str):
        available_commands = [
            self.STARTUP,
            self.STARTUP_WITH_PHASE,
            self.ARBITRARY_TEXT,
            self.ARBITRARY_TEXT_ICON,
            self.ARBITRARY_ICON,
            self.CLEAR,
        ]
        super(ForegroundCommand, self).__init__(command, available_commands)
 
class BackgroundCommand(PaintingCommand):
    """
    Commands related to background painting.
    They are meant to be used in the (currently) "top-left" area of the screen, but they can be used in other areas as well.
    """

    THINKING: str = "THINKING"
    NETWORKING: str = "NETWORKING"
    SPEAKING: str = "SPEAKING"

    HOLDER_PERCENTAGE: str = "HOLDER_PERCENTAGE"
    ERROR: str = "ERROR"

    def __init__(self, command: str):
        available_commands = [
            self.THINKING,
            self.NETWORKING,
            self.SPEAKING,
            self.HOLDER_PERCENTAGE,
            self.ERROR,
            self.CLEAR,
        ]
        super(BackgroundCommand, self).__init__(command, available_commands)