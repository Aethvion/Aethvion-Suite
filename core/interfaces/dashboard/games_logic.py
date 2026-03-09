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
                "easy":   "The rule should be simple (e.g., multiply by 2, add 5, reverse the string, append characters). Inputs will typically be single small integers or short words.",
                "medium": "The rule should be moderate complexity (e.g., count vowels * 10, concatenate first and last char, square the length, sort characters alphabetically).",
                "hard":   "The rule should be complex and non-obvious (e.g., sum of ASCII values mod 97, Fibonacci position lookup, count unique characters squared, Caesar cipher shift by length).",
                "expert": "The rule should be very hard — multi-step, combinatorial, or involving unusual mathematical/string operations."
            }
            hint = difficulty_hints.get(self.difficulty, difficulty_hints["easy"])
            return f"""You are the Game Master AI for 'Logic Quest: The Black Box'.

== RULES ==
- You hold a SECRET TRANSFORMATION RULE in your mind. NEVER reveal it directly.
- When the user tests an input, apply your secret rule and return ONLY the output value.
- When the user guesses the rule, evaluate their guess generously — accept paraphrases and synonyms if they capture the essence.
- When starting a new game, silently pick a rule and confirm you're ready.
- {hint}

== RESPONSE FORMAT ==
You must respond ONLY with valid JSON. No prose, no markdown.

For a new game start: {{"action": "ready", "hint": "<short vague hint like 'involves numbers' or 'about the characters'>", "max_attempts": <int>}}
For a test input: {{"action": "test_result", "output": "<result>", "comment": "<optional witty 1-sentence comment, never reveal the rule>"}}
For a correct guess: {{"action": "correct", "rule": "<your actual rule, now revealed>", "message": "<congratulations message>"}}
For a wrong guess: {{"action": "wrong", "message": "<hint nudge without revealing the rule>"}}
For a hint request: {{"action": "hint", "hint": "<a useful but vague nudge>"}}"""
        return "You are a game master AI."

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
