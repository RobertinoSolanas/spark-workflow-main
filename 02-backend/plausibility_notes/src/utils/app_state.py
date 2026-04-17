"""Class used to store current app state."""


class AppState:
    def __init__(self):
        self.startup_complete = False


app_state = AppState()
