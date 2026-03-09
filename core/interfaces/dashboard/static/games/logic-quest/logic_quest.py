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

class LogicQuestGame(BaseGame):
    def get_system_prompt(self) -> str:
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
6. Reveal Answer: {{"action": "reveal", "rule": "reveal the rule", "message": "explanation"}}

Current Difficulty: {self.difficulty}
{hint}"""

    def get_opening_prompt(self) -> str:
        return f"Start a new Black Box game. Difficulty: {self.difficulty}. Pick your secret rule. Respond ONLY with the JSON object."
