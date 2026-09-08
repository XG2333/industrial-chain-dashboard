from enum import Enum


class RuleSource(str, Enum):
    DEFAULT_PLACEHOLDER = "DEFAULT_PLACEHOLDER"
    USER_RULES = "USER_RULES"
    SAVED_RULE_SET = "SAVED_RULE_SET"


class RuleSetStatus(str, Enum):
    DRAFT = "DRAFT"
    PARSED = "PARSED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    INVALID = "INVALID"


class VariableStatus(str, Enum):
    UNPROCESSED = "UNPROCESSED"
    INCLUDE = "INCLUDE"
    EXCLUDE = "EXCLUDE"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ClassificationMethod(str, Enum):
    UNCLASSIFIED = "UNCLASSIFIED"
    MOCK = "MOCK"
    HEURISTIC = "HEURISTIC"
    LLM = "LLM"


class DataType(str, Enum):
    NUMERIC = "NUMERIC"
    DATE = "DATE"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    EMPTY = "EMPTY"
    MIXED = "MIXED"
