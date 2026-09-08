class LLMError(Exception):
    """Base exception for LLM provider and classification failures."""


class LLMConfigurationError(LLMError):
    """Raised when LLM configuration is invalid."""


class LLMRealCallDisabledError(LLMConfigurationError):
    """Raised when a real provider is requested without REAL_LLM_ENABLED=true."""


class LLMAuthenticationError(LLMConfigurationError):
    """Raised when the provider rejects or is missing authentication."""


class LLMInsufficientBalanceError(LLMError):
    """Raised when the provider reports insufficient balance."""


class LLMPermissionError(LLMError):
    """Raised when the provider denies permission for the requested operation."""


class LLMRateLimitError(LLMError):
    """Raised when the provider reports rate limiting."""


class LLMTimeoutError(LLMError):
    """Raised when the provider request times out."""


class LLMConnectionError(LLMError):
    """Raised when the provider cannot be reached."""


class LLMInvalidRequestError(LLMError):
    """Raised when the request itself is invalid."""


class LLMStructuredOutputError(LLMError):
    """Raised when structured output cannot be parsed or is inconsistent."""


class LLMRefusalError(LLMError):
    """Raised when the provider refuses the request."""


class LLMEmptyResponseError(LLMError):
    """Raised when the provider returns no usable content."""


class LLMProviderError(LLMError):
    """Raised for other provider-side failures."""
