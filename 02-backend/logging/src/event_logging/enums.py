from enum import Enum


class LogEventDefault(str, Enum):
    DOCUMENT_UPLOAD = "document_upload"
    DOCUMENT_DOWNLOAD = "document_download"
    GENERAL = "general"
    API_REQUEST = "api_request"
    API_RESPONSE = "api_response"
    VALIDATION_FAILURE = "validation_failure"
    RESOURCE_NOT_FOUND = "resource_not_found"
    EXTERNAL_SERVICE_INTERACTION = "external_service_interaction"
    NOTIFICATION_SENT = "notification_sent"
    SEARCH_QUERY = "search_query"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    DB_READ = "db_read"
    DB_WRITE = "db_write"
    DB_ERROR = "db_error"
    DB_SUCCESS = "db_success"
    DB_COMMIT = "db_commit"
    DB_ROLLBACK = "db_rollback"
    AGENT_CALL = "agent_call"
    AGENT_RESPONSE = "agent_response"
    AGENT_ERROR = "agent_error"



class LogEventSystem(str, Enum):
    CONTAINER_LIFECYCLE = "container_lifecycle"
    HEALTH_CHECK = "health_check"
    DB_CONNECTION = "db_connection"
    MEMORY_USAGE = "memory_usage"
    GARBAGE_COLLECTION = "garbage_collection"
    LLM_LATENCY = "llm_latency"
    JOB_TRIGGER = "job_trigger"
    ALERT = "alert"


class LogEventAuth(str, Enum):
    PERMISSION_ERROR = "permission_error"
    CONFIG_CHANGE = "config_change"
    ACCESS_MODIFICATION = "access_modification"
    LOGIN = "login"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"


class LogEventLegal(str, Enum):
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_REMOVED = "document_removed"
    DOCUMENT_UPDATED = "document_updated"
    HUMAN_REJECTION = "human_rejection"
    HUMAN_CORRECTION = "human_correction"
    HUMAN_APPROVAL = "human_approval"
    AGENT_SUGGESTION = "agent_suggestion"
    WORKFLOW_TRIGGER = "workflow_trigger"


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


class EventAction(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    CHANGE = "change"
    AUTHENTICATE = "authenticate"
    AUTHORIZE = "authorize"
    ACCESS = "access"
    VALIDATE = "validate"
    NOTIFY = "notify"
    HEALTH = "health"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    CONFIRMATION = "confirmation"
    CORRECTION = "correction"
    REJECTION = "rejection"
    CLICK = "click"
    NAVIGATE = "navigate"
    INPUT = "input"
    FOCUS = "focus"
    BLUR = "blur"
    TOKEN_REFRESH = "token_refresh"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class EventCategory(str, Enum):
    API = "api"
    DATABASE = "database"
    FILE = "file"
    AUTHENTICATION = "authentication"
    SECURITY = "security"
    AI = "ai"
    SERVICE = "service"



class EventOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"
    IN_PROGRESS = "in_progress"


class EventType(str, Enum):
    ACCESS = "access"
    CHANGE = "change"
    ERROR = "error"
    INFO = "info"


class ServiceName(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    DB = "db"
    AI = "ai"


class EventKind(str, Enum):
    ALERT = "alert"
    EVENT = "event"


class ServiceComponent(str, Enum):
    LOAD_BALANCER = "load_balancer"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    USER = "user"
    LLM = "llm"
    API_GATEWAY = "api_gateway"
    SESSION = "session"
    


class UserType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    SERVICE = "service"


class AiDecisionHumanOverride(str, Enum):
    REVIEW = "review"
    APPROVE = "approve"
    OVERRIDE = "override"
    FEEDBACK = "feedback"


class DatabaseOperation(str, Enum):
    CREATE = "create"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
