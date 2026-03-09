"""
Misaka Cipher - Games Engine
Modular Loader.
"""

import json
import uuid
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.utils import get_logger

# Helper to load modules from static folder
def load_game_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Get paths
STATIC_GAMES = Path(__file__).parent / "static" / "games"
LogicQuestGame = load_game_module("logic_quest", str(STATIC_GAMES / "logic-quest" / "logic_quest.py")).LogicQuestGame
BlackJackGame = load_game_module("blackjack", str(STATIC_GAMES / "blackjack" / "blackjack.py")).BlackJackGame

logger = get_logger(__name__)

class AIGameSession:
    def __init__(self, session_id: str, game_type: str, difficulty: str, model: str):
        self.session_id = session_id
        self.game_type = game_type # internal id: "logic-quest", "playing-cards" (to stay compatible with current routes)
        self.difficulty = difficulty
        self.model = model
        self.history: List[Dict[str, Any]] = []
        self.attempts = 0
        self.completed = False
        self.score = 0
        self.ai_context: List[Dict[str, str]] = []
        
        # Load the specific modular game instance
        if game_type == "logic-quest":
            self.game = LogicQuestGame(difficulty)
        elif game_type == "blackjack":
            self.game = BlackJackGame(difficulty)
        else:
            self.game = None

    def _build_system_prompt(self) -> str:
        if self.game:
            return self.game.get_system_prompt()
        return "You are a game master AI. Respond in JSON."

    def get_opening_message(self) -> Dict[str, Any]:
        content = "Start a new game."
        if self.game:
            content = self.game.get_opening_prompt()
            
        return {
            "role": "user",
            "content": content
        }

class AIGameManager:
    def __init__(self):
        self.sessions: Dict[str, AIGameSession] = {}

    def create_session(self, game_type: str, difficulty: str, model: str) -> AIGameSession:
        session_id = str(uuid.uuid4())
        session = AIGameSession(session_id, game_type, difficulty, model)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[AIGameSession]:
        return self.sessions.get(session_id)

    def delete_session(self, session_id: str):
        self.sessions.pop(session_id, None)

_ai_game_manager = AIGameManager()

def get_ai_game_manager() -> AIGameManager:
    return _ai_game_manager
