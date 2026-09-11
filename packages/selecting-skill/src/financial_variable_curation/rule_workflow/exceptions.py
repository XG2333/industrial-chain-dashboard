class RuleWorkflowError(Exception):
    """Raised when rule parsing, validation, conflict detection, or compilation fails."""


class RuleSourceError(RuleWorkflowError):
    """Raised when the rule source file is invalid."""
