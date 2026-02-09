from fastapi import HTTPException, status

class ChatError(Exception):
    """Base class for chat-related errors"""
    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ChatValidationError(ChatError):
    """Raised when request validation fails"""
    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_400_BAD_REQUEST)

class ChatRateLimitError(ChatError):
    """Raised when LLM API rate limits are hit"""
    def __init__(self, message: str = "Rate limit exceeded. Please try again soon."):
        super().__init__(message, status_code=status.HTTP_429_TOO_MANY_REQUESTS)

class ChatDatabaseError(ChatError):
    """Raised when Supabase operations fail"""
    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

class ChatTimeoutError(ChatError):
    """Raised when LLM calls or database operations time out"""
    def __init__(self, message: str = "Request timed out."):
        super().__init__(message, status_code=status.HTTP_504_GATEWAY_TIMEOUT)

class ChatInternalError(ChatError):
    """Raised for unexpected internal failures"""
    def __init__(self, message: str):
        super().__init__(message, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
