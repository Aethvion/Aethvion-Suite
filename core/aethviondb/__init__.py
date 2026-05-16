"""
core/aethviondb — AethvionDB Knowledge Database Engine

Every entity (person, place, event, concept…) shares an identical JSON
envelope. The name-to-ID index must exist before any entity file is created.

Multiple databases are supported — each is an independent directory with
its own entities/ folder and name_index.json.

Public surface
--------------
from core.aethviondb import NameIndex, EntityWriter, Validator, ContentDistiller
"""

from .name_index import NameIndex
from .entity_writer import EntityWriter
from .validator import Validator
from .distiller import ContentDistiller

__all__ = ["NameIndex", "EntityWriter", "Validator", "ContentDistiller"]
