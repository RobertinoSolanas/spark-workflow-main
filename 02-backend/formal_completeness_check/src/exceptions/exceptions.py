"""Common exceptions for the microservice."""


class NotFoundError(Exception):
    """Raised when a requested entity cannot be found."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ForbiddenError(Exception):
    """Raised when an operation is not permitted on the target resource."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
