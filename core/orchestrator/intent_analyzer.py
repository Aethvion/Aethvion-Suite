"""
Aethvion Suite - Intent Analyzer
Classifies user messages into actionable intents
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from core.nexus_core import NexusCore, Request
from core.utils import get_logger

logger = get_logger(__name__)


class IntentType(Enum):
    """Categories of user intent."""
    CHAT = "chat"                    # General conversation
    QUERY = "query"                  # Information retrieval
    ANALYZE = "analyze"              # Data analysis task
    CREATE = "create"                # Tool generation request
    EXECUTE = "execute"              # Task execution
    SYSTEM = "system"                # System control/status
    UNKNOWN = "unknown"              # Unable to classify


@dataclass
class IntentAnalysis:
    """Result of intent analysis."""
    intent_type: IntentType
    confidence: float
    prompt: str
    domain: Optional[str] = None
    action: Optional[str] = None
    object: Optional[str] = None
    parameters: Dict[str, Any] = None
    requires_tool: bool = False
    tool_name: Optional[str] = None
    requires_agent: bool = False
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class IntentAnalyzer:
    """
    Analyzes user messages to determine intent and extract parameters.
    
    Uses Nexus Core AI to classify intents and extract structured data
    for orchestrator action planning.
    """
    
    def __init__(self, nexus: NexusCore):
        """
        Initialize intent analyzer.
        
        Args:
            nexus: NexusCore instance for AI analysis
        """
        self.nexus = nexus
        logger.info("Intent Analyzer initialized")
    
    def analyze(self, user_message: str, trace_id: str = None, force_chat: bool = False, source: str = "unknown") -> IntentAnalysis:
        """
        Analyze user message to determine intent.
        
        Args:
            user_message: User's input message
            trace_id: Optional trace ID for context
            force_chat: If True, bypass analysis and force CHAT intent
            source: Source of the request (dashboard, discord, etc.)
            
        Returns:
            IntentAnalysis with classified intent and parameters
        """
        if force_chat:
            logger.info(f"[{trace_id}] Force CHAT intent requested")
            return IntentAnalysis(
                intent_type=IntentType.CHAT,
                confidence=1.0,
                prompt=user_message,
                parameters={}
            )
            
        logger.info(f"Analyzing intent for message: {user_message[:50]}...")
        
        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(user_message)
        
        # Send to Nexus Core
        request = Request(
            prompt=analysis_prompt,
            request_type="generation",
            temperature=0.3,  # Low temperature for consistent classification
            max_tokens=500,
            trace_id=trace_id,
            metadata={"source": source}
        )
        
        response = self.nexus.route_request(request)
        
        if not response.success:
            logger.warning(f"Intent analysis failed: {response.error}")
            return self._fallback_analysis(user_message)
        
        # Parse AI response
        return self._parse_analysis(response.content, user_message)
    
    def _build_analysis_prompt(self, user_message: str) -> str:
        """Build prompt for intent classification."""
        return f"""You are an intent classifier for Aethvion Suite system. Analyze this user message and respond with JSON.

User Message: "{user_message}"

Classify the intent into one of these categories:
- CHAT: General conversation, creative writing (stories, poems), brainstorming, simple explanations.
- QUERY: Information retrieval (status, list tools, search memory, "what tools do I have?")
- ANALYZE: Data analysis requests (analyze stock, review code, generate insights)
- CREATE: Tool creation requests (create tool, forge capability, build function)
- EXECUTE: Direct task execution (summarize text, calculate something, perform action)
- SYSTEM: System control (show status, check health, restart)

IMPORTANT RULES:
1. Prefer CHAT for tasks that can be answered with pure text generation (stories, summaries, simple code snippets).
2. ONLY use tools (ANALYZE/EXECUTE/CREATE) if the request requires external data, complex computation, file I/O, or specific system changes.
3. If the user says "no tool" or "don't use tool", classify as CHAT or EXECUTE without tool requirements.
4. Do NOT create tools for one-off creative tasks like writing a story.

Extract parameters if applicable:
- domain: Which domain? (Finance, Data, Code, Security, System, etc.)
- action: What action? (Analyze, Generate, Review, Calculate, etc.)
- object: What object? (Stock, Dataset, Code, Report, etc.)
- requires_tool: Does this need a specific tool? (true/false)
- tool_name: If requires_tool, what tool? (Finance_Fetch_Market, etc.)  If "no tool" requested, must be null.
- requires_agent: Does this need to spawn an agent? (true/false)

Respond ONLY with JSON in this exact format:
{{
  "intent_type": "ANALYZE",
  "confidence": 0.95,
  "domain": "Finance",
  "action": "Analyze",
  "object": "Stock",
  "requires_tool": true,
  "tool_name": "Finance_Fetch_Market",
  "requires_agent": true,
  "parameters": {{"ticker": "TSLA", "timeframe": "10-year"}}
}}"""
    
    def _parse_analysis(self, ai_response: str, original_message: str) -> IntentAnalysis:
        """Parse AI response into IntentAnalysis."""
        import json
        import re
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find JSON without code blocks
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    raise ValueError("No JSON found in response")
            
            data = json.loads(json_str)
            
            # Map intent string to enum
            intent_str = data.get('intent_type', 'UNKNOWN').upper()
            try:
                intent_type = IntentType[intent_str]
            except KeyError:
                logger.warning(f"Unknown intent type: {intent_str}, defaulting to UNKNOWN")
                intent_type = IntentType.UNKNOWN
            
            return IntentAnalysis(
                intent_type=intent_type,
                confidence=float(data.get('confidence', 0.5)),
                prompt=original_message,
                domain=data.get('domain'),
                action=data.get('action'),
                object=data.get('object'),
                parameters=data.get('parameters', {}),
                requires_tool=data.get('requires_tool', False),
                tool_name=data.get('tool_name'),
                requires_agent=data.get('requires_agent', False)
            )
            
        except Exception as e:
            logger.error(f"Failed to parse intent analysis: {str(e)}")
            logger.debug(f"AI response was: {ai_response}")
            return self._fallback_analysis(original_message)
    
    def _fallback_analysis(self, user_message: str) -> IntentAnalysis:
        """Fallback analysis using simple heuristics."""
        message_lower = user_message.lower()
        
        # Simple keyword-based classification
        if any(word in message_lower for word in ['status', 'health', 'how are you', 'diagnostic']):
            intent = IntentType.SYSTEM
        elif any(word in message_lower for word in ['create', 'forge', 'build', 'generate tool']):
            intent = IntentType.CREATE
        elif any(word in message_lower for word in ['analyze', 'review', 'examine', 'study']):
            intent = IntentType.ANALYZE
        elif any(word in message_lower for word in ['search', 'find', 'list', 'show', 'what']):
            intent = IntentType.QUERY
        elif any(word in message_lower for word in ['execute', 'run', 'perform', 'do']):
            intent = IntentType.EXECUTE
        else:
            intent = IntentType.CHAT
        
        logger.info(f"Using fallback classification: {intent.value}")
        
        return IntentAnalysis(
            intent_type=intent,
            confidence=0.3,  # Low confidence for fallback
            prompt=user_message,
            parameters={}
        )
    
    def extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text."""
        # Simple implementation - can be enhanced with NLP
        import re
        
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                     'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been'}
        
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords[:10]  # Top 10 keywords
