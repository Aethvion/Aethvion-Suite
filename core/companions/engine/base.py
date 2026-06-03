"""
core/companions/engine/base.py
Shared base class for companion engine components.
"""
from __future__ import annotations
from pathlib import Path
from core.utils import get_logger


class CompanionComponent:
    """
    Shared base for CompanionMemory, CompanionHistory, and any future
    engine components.

    Centralises the repeated init pattern across companion sub-components:
      - stores the component directory and companion name
      - creates the directory on construction (idempotent)
      - provides prefixed log helpers so every log line is tagged with the
        companion name and routed through a logger keyed to the *concrete*
        subclass module (e.g. core.companions.engine.memory, not base).

    Adding a new cross-cutting concern (observability hook, storage-backend
    switch, etc.) now requires a change in one place instead of every component.
    """

    def __init__(self, data_dir: Path, companion_name: str = "Companion") -> None:
        self._dir = data_dir
        self._name = companion_name
        # Keyed to the concrete subclass module so log sources stay accurate.
        self._logger = get_logger(type(self).__module__)
        self._dir.mkdir(parents=True, exist_ok=True)

    # Prefixed log helpers — subclasses call these instead of bare logger.*

    def _info(self, msg: str) -> None:
        self._logger.info(f"{self._name}: {msg}")

    def _warning(self, msg: str) -> None:
        self._logger.warning(f"{self._name}: {msg}")

    def _error(self, msg: str) -> None:
        self._logger.error(f"{self._name}: {msg}")
