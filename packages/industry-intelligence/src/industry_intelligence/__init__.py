"""Opt-in intelligence layer for the industry-chain dashboard.

Importing this package never starts a server, indexes files, calls a model, or
changes an existing workbook. Every integration is invoked explicitly.
"""

from .config import IntelligenceSettings
from .models import KnowledgeChunk, SearchHit

__all__ = ["IntelligenceSettings", "KnowledgeChunk", "SearchHit"]
__version__ = "0.1.0"
