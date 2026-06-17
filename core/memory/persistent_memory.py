from pathlib import Path
from typing import Dict, List, Any
from core.utils import get_logger, utcnow_iso, load_json, atomic_json_write

logger = get_logger(__name__)

from core.utils.paths import PERSISTENT_MEMORY_JSON

# Default location for persistent memory
MEMORY_PATH = PERSISTENT_MEMORY_JSON

class PersistentMemory:
    """
    Manages persistent memory for the chat system.
    Data is stored per topic in a JSON file.
    """
    
    def __init__(self, path: Path = MEMORY_PATH):
        self.path = path
        self.memory: Dict[str, Dict[str, Any]] = {}
        self._load()
        
    def _load(self):
        """Load memory from disk."""
        self.memory = load_json(self.path, default={})
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
        else:
            logger.info(f"Loaded persistent memory ({len(self.memory)} topics)")

    def _save(self):
        """Save memory to disk atomically."""
        atomic_json_write(self.path, self.memory)

    def get_all_memory(self) -> str:
        """Returns all memory as a formatted string for prompting."""
        if not self.memory:
            return ""
        
        lines = ["### PERSISTENT MEMORY ###"]
        for topic, data in self.memory.items():
            content = data.get('content', '')
            if content:
                lines.append(f"Topic: {topic}")
                lines.append(content)
                lines.append("")
        return "\n".join(lines)

    def update_topic(self, topic: str, content: str):
        """Update or add a topic to memory."""
        self.memory[topic] = {
            "content": content,
            "updated_at": utcnow_iso()
        }
        self._save()
        logger.info(f"Updated persistent memory topic: {topic}")

    def delete_topic(self, topic: str):
        """Delete a topic from memory."""
        if topic in self.memory:
            del self.memory[topic]
            self._save()
            logger.info(f"Deleted persistent memory topic: {topic}")

    def clear_all(self):
        """Clear all memory."""
        self.memory = {}
        self._save()

    def extract_and_update(self, text: str) -> tuple[str, List[Dict[str, Any]]]:
        """
        Extract <memory_topic> tags from text, update files, and return cleaned text and update info.
        Format: <memory_topic title="Topic Name">Content here</memory_topic>
        """
        import re
        updates = []
        # Find all occurrences
        matches = list(re.finditer(r'<memory_topic\s+title=["\'](.*?)["\']>(.*?)</memory_topic>', text, re.DOTALL))
        
        # Process in reverse to maintain offsets while deleting
        cleaned_text = text
        for match in reversed(matches):
            topic = match.group(1).strip()
            content = match.group(2).strip()
            
            if topic and content:
                self.update_topic(topic, content)
                updates.append({"topic": topic, "content": content})
                
            # Remove tag from text
            start, end = match.span()
            cleaned_text = cleaned_text[:start] + cleaned_text[end:]
        
        return cleaned_text.strip(), updates

_instance = None

def get_persistent_memory() -> PersistentMemory:
    """Get global persistent memory instance."""
    global _instance
    if _instance is None:
        _instance = PersistentMemory()
    return _instance
