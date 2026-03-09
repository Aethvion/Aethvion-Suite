from abc import ABC, abstractmethod

class BaseGame(ABC):
    def __init__(self, difficulty: str):
        self.difficulty = difficulty

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def get_opening_prompt(self) -> str:
        pass

class BlackJackGame(BaseGame):
    def get_system_prompt(self) -> str:
        return f"""You are the AI Dealer in 'Blackjack'. Respond ONLY with valid JSON.

JSON TEMPLATE:
{{
  "action": "dealt"|"draw_result"|"stay_result"|"hint",
  "player_hand": [{{"rank":"rank","suit":"symbol"}}, ...],
  "ai_hand": [{{"rank":"rank","suit":"symbol"}}, ...],
  "player_score": int,
  "ai_score": int,
  "deck_count": int,
  "message": "text",
  "completed": bool,
  "result": "win"|"loss"|"push"|null
}}

RULES:
- Objective: Total closer to 21 than dealer wins.
- Values: 10/J/Q/K = 10. Ace = 1 or 11.
- Dealer hits on 16 or lower, stays 17+.
- DIFFICULTY: {self.difficulty}.

CRITICAL:
1. ALWAYS provide BOTH hands.
2. USE SYMBOLS: ♥, ♦, ♣, ♠.
3. NO PREAMBLE. NO TRUNCATION.
"""

    def get_opening_prompt(self) -> str:
        return "Deal a new hand of Blackjack. Response MUST be valid JSON with 'player_hand', 'ai_hand', and 'player_score'."
