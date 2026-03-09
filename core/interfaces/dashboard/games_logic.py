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
        self.result = None # "win", "loss", "push"
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

    def save_history(self):
        """Persist the game session to memory storage."""
        try:
            from datetime import datetime
            
            root = Path(__file__).parent.parent.parent.parent
            storage_dir = root / "data" / "memory" / "storage" / "games" / self.game_type
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            history_file = storage_dir / "history.json"
            
            all_history = []
            if history_file.exists():
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        all_history = json.load(f)
                except:
                    all_history = []

            # Session data snapshot
            session_data = {
                "session_id": self.session_id,
                "game_type": self.game_type,
                "difficulty": self.difficulty,
                "model": self.model,
                "attempts": self.attempts,
                "completed": self.completed,
                "score": self.score,
                "result": self.result,
                "history": self.history,
                "updated_at": datetime.now().isoformat()
            }

            # Update existing or append
            found_idx = -1
            for i, entry in enumerate(all_history):
                if entry.get("session_id") == self.session_id:
                    found_idx = i
                    break
            
            if found_idx >= 0:
                # Preserve created_at if it existed
                if "created_at" in all_history[found_idx]:
                    session_data["created_at"] = all_history[found_idx]["created_at"]
                all_history[found_idx] = session_data
            else:
                session_data["created_at"] = session_data["updated_at"]
                all_history.append(session_data)
            
            # Keep only last 200 sessions per game
            if len(all_history) > 200:
                all_history = all_history[-200:]

            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(all_history, f, indent=2)
                
            logger.debug(f"[{self.session_id[:8]}] Session history updated in {history_file}")
        except Exception as e:
            logger.error(f"Failed to save game history: {e}")

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
