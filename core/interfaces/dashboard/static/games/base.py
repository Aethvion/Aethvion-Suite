from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseGame(ABC):
    def __init__(self, difficulty: str):
        self.difficulty = difficulty

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the system prompt for the AI."""
        pass

    @abstractmethod
    def get_opening_prompt(self) -> str:
        """Return the opening prompt for the AI."""
        pass
