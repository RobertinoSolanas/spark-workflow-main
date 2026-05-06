class NotFoundError(Exception):
    """Custom exception for not found errors."""

    def __init__(self, message: str = "Resource not found"):
        """Initialize the exception with a message."""
        super().__init__(message)


class OperationFailedError(Exception):
    """Custom exception for operation failures."""

    def __init__(self, message: str = "Operation failed unexpectedly"):
        """Initialize the exception with a message."""
        super().__init__(message)
