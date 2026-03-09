"""
Misaka Cipher - Games Engine
AI-driven game session management.
Each game delegates all intelligence to an AI model.
"""

import json
import uuid
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from core.utils import get_logger

logger = get_logger(__name__)


class AIGameSession:
    """
    A single AI-powered game session.
    
    The AI (model) is responsible for:
    1. Generating the hidden rule / puzzle on session start
    2. Processing test inputs against the secret rule
    3. Evaluating guess attempts
    4. Providing hints (if the game supports it)
    """

    def __init__(self, session_id: str, game_type: str, difficulty: str, model: str):
        self.session_id = session_id
        self.game_type = game_type
        self.difficulty = difficulty
        self.model = model   # specific model ID or "auto"
        self.history: List[Dict[str, Any]] = []
        self.attempts = 0
        self.completed = False
        self.score = 0
        self.ai_context: List[Dict[str, str]] = []  # conversation history with the AI game master

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the game master AI based on game type and difficulty."""
        if self.game_type == "logic-quest":
            difficulty_hints = {
                "easy":   "The rule should be simple (e.g., multiply by 2, add 5, reverse the string). Inputs will be small integers or words.",
                "medium": "The rule should be moderate (e.g., count vowels * 10, concatenate first and last char, square the length).",
                "hard":   "The rule should be complex (e.g., sum of ASCII values mod 97, Fibonacci position lookup, Caesar shift).",
                "expert": "The rule should be very hard — multi-step or combinatorial logic."
            }
            hint = difficulty_hints.get(self.difficulty, difficulty_hints["easy"])
            return f"""You are the Game Master AI for 'Logic Quest: The Black Box'.

== RULES ==
- You hold a SECRET rule. Inputs → Outputs. 
- NEVER reveal the rule in the 'comment' or 'hint'.
- When the user tests an input: apply the rule and return valid JSON.
- When the user guesses: evaluate generously but accurately.

== STRICT RESPONSE FORMAT (JSON ONLY) ==
Every response MUST be a single JSON object. No markdown fences if possible, no preamble.

1. New Game: {{"action": "ready", "hint": "vague hint", "max_attempts": 10}}
2. Test Input: {{"action": "test_result", "output": "result", "comment": "witty remark"}}
3. Correct Guess: {{"action": "correct", "rule": "reveal rule", "message": "congrats"}}
4. Wrong Guess: {{"action": "wrong", "message": "nudge hint"}}
5. Hint Request: {{"action": "hint", "hint": "help nudge"}}

Current Difficulty: {self.difficulty}
{hint}"""
        return "You are a game master AI. Respond in JSON."

    def get_opening_message(self) -> Dict[str, Any]:
        """Get the message to send to AI on session start."""
        return {
            "role": "user",
            "content": f"Start a new Black Box game. Difficulty: {self.difficulty}. Pick your secret rule and tell me you're ready."
        }


class AIGameManager:
    """Manages all AI game sessions."""
    
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


# Global singleton
_ai_game_manager = AIGameManager()

def get_ai_game_manager() -> AIGameManager:
    return _ai_game_manager
