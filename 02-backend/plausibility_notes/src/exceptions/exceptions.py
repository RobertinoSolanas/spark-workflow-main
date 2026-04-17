"""Common exceptions for the microservice."""


class NotFoundError(Exception):
    """Raised when a requested entity cannot be found."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class OperationFailedError(Exception):
    """Raised when an operation fails unexpectedly."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
