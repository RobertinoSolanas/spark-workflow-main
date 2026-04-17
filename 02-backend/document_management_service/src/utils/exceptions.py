class DocumentServiceBaseError(Exception):
    """Base exception for the DocumentService."""


class FileValidationError(DocumentServiceBaseError):
    """Base exception for file validation errors."""


class FileInvalidFileTypeError(FileValidationError):
    """Raised when an invalid file type is encountered."""


class FileInvalidFileExtensionError(FileValidationError):
    """Raised when an invalid file extension is encountered."""


class WorkflowRequiresApprovalError(DocumentServiceBaseError):
    """Raised when a workflow is started and another one requires approval."""


class WorkflowInRunningStateError(DocumentServiceBaseError):
    """Raised when a workflow is started and another one is in running state."""


class WorkflowInPendingStateError(DocumentServiceBaseError):
    """Raised when a workflow is started and another one is in pending state."""


class WorkflowAlreadyApprovedError(DocumentServiceBaseError):
    """Exception raised when a workflow is already approved."""


class WorkflowAlreadyRejectedError(DocumentServiceBaseError):
    """Exception raised when a workflow is already rejected."""


class WorkflowIncorrectStatusError(DocumentServiceBaseError):
    """Exception raised when a workflow staus is incorrect."""


class WorkflowNotFoundError(DocumentServiceBaseError):
    """Exception raised when a workflow does not exist."""


class WorkflowValidateDiffError(DocumentServiceBaseError):
    """Exception raised when a workflow diff validation fails."""
