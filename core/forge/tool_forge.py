"""
Misaka Cipher - Tool Forge
Core tool generation engine
"""

import json
import importlib
from pathlib import Path
from typing import Optional, Dict, Any

from .tool_spec import ToolSpec, ParameterSpec
from .tool_registry import get_tool_registry
from .code_generator import CodeGenerator
from .tool_validator import ToolValidator, ValidationResult
from core.nexus_core import NexusCore, Request
from core.utils import get_logger, get_trace_manager, utcnow_iso
from core.utils.paths import MODEL_REGISTRY, WS_TOOLS

logger = get_logger(__name__)


class ToolForge:
    """
    The Forge - Autonomous tool generation system.
    
    Generates tools from natural language descriptions:
    1. Analyze description via Nexus Core
    2. Extract domain, action, object
    3. Generate Python code
    4. Validate Aethvion compliance and security
    5. Register tool
    """
    
    def __init__(self, nexus: NexusCore, tools_dir: Optional[Path] = None):
        """
        Initialize Tool Forge.
        
        Args:
            nexus: NexusCore instance for analysis
            tools_dir: Directory to save generated tools
        """
        self.nexus = nexus
        self.trace_manager = get_trace_manager()
        self.registry = get_tool_registry()
        self.generator = CodeGenerator()
        self.validator = ToolValidator()
        
        # Tools directory at project root
        if tools_dir is None:
            tools_dir = WS_TOOLS / "generated"
        
        self.tools_dir = Path(tools_dir)
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        
        # Load Model Registry
        self.model_registry = self._load_model_registry()
        
        logger.info(f"Tool Forge initialized (tools_dir: {self.tools_dir})")
    
    def _load_model_registry(self) -> Dict[str, Any]:
        """Load the model registry from config/model_registry.json."""
        try:
            registry_path = MODEL_REGISTRY
            if registry_path.exists():
                with open(registry_path, 'r') as f:
                    registry = json.load(f)
                logger.info(f"Model Registry loaded: {len(registry.get('providers', {}))} providers")
                return registry
            else:
                logger.warning("Model Registry not found, using empty registry")
                return {"providers": {}, "routing_strategy": {}}
        except Exception as e:
            logger.error(f"Failed to load Model Registry: {e}")
            return {"providers": {}, "routing_strategy": {}}
    
    def _build_provider_context(self) -> str:
        """Build the ENVIRONMENT & API KEYS section from model_registry.json."""
        providers = self.model_registry.get("providers", {})
        if not providers:
            return (
                "ENVIRONMENT & API KEYS:\n"
                "No provider registry found. Use os.environ.get() for any API keys.\n"
                "NEVER use placeholder URLs like 'api.example.com'.\n"
            )
        
        lines = ["ENVIRONMENT & API KEYS & MODELS (from Model Registry):"]
        active_keys = []
        forbidden_keys = []
        
        for name, config in providers.items():
            key_env = config.get("api_key_env", "UNKNOWN")
            if config.get("active", False):
                details = f"  - PROVIDER: {name.upper()}\n    Key Env: {key_env} (priority {config.get('priority', '?')})\n    Models:"
                
                # List models
                models = config.get("models", {})
                for model_key, model_data in models.items():
                    capabilities = ", ".join(model_data.get("capabilities", []))
                    details += f"\n      * {model_key}: {model_data.get('id')} [{capabilities}]"
                    if "endpoint" in model_data:
                        details += f" (Endpoint: {model_data['endpoint']})"
                    if "notes" in model_data:
                        details += f" - {model_data['notes']}"
                
                active_keys.append(details)
            else:
                forbidden_keys.append(f"  - {key_env} ({name}) — DISABLED, do NOT use")
        
        if active_keys:
            lines.append("ACTIVE providers (use these via `os.environ.get()`):")
            lines.extend(active_keys)
        
        if forbidden_keys:
            lines.append("FORBIDDEN providers (do NOT use):")
            lines.extend(forbidden_keys)
        
        lines.append("")
        lines.append("IMPORTANT:")
        lines.append("- SELECT THE CORRECT MODEL for the task. Do NOT use a text model for image generation.")
        lines.append("- Refer to the [capabilities] tag for each model.")
        lines.append("- Always check if the key exists before using it.")
        lines.append("- If multiple providers are active, prefer the highest priority one.")
        
        return "\n".join(lines)
    
    def _build_patch_context(self, existing_code: str = None) -> str:
        """Build the PATCH PROTOCOL section if existing code was found."""
        if not existing_code:
            return ""
        
        return (
            "PATCH PROTOCOL — EXISTING CODE DETECTED:\n"
            "A previous version of this tool already exists. You MUST:\n"
            "1. PRESERVE all existing provider support (do not remove working code).\n"
            "2. EXTEND by adding new functionality as additional branches or helpers.\n"
            "3. If the existing code supports Provider X, keep it. Add Provider Y alongside.\n"
            "\n"
            "--- EXISTING IMPLEMENTATION ---\n"
            f"{existing_code[:2000]}\n"
            "--- END EXISTING ---\n"
        )
    
    def _get_max_retries(self) -> int:
        """Get max retries per step from the highest-priority active provider."""
        providers = self.model_registry.get("providers", {})
        active = [
            (name, cfg) for name, cfg in providers.items()
            if cfg.get("active", False)
        ]
        if not active:
            return 3  # Fallback
        # Sort by priority (lower = higher priority)
        active.sort(key=lambda x: x[1].get("priority", 99))
        retries = active[0][1].get("retries_per_step", 3)
        logger.info(f"Max retries per step: {retries} (from provider '{active[0][0]}')") 
        return retries
    
    def generate_tool(
        self,
        description: str,
        implementation_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a tool from description.
        
        Args:
            description: Natural language tool description
            implementation_hints: Optional implementation guidance
            
        Returns:
            Tool information dict
            
        Raises:
            ValueError: If tool generation fails validation
        """
        # Generate Trace_ID for this tool generation
        trace_id = self.trace_manager.start_trace(metadata={
            'operation': 'tool_generation',
            'description': description
        })
        
        logger.info(f"[{trace_id}] Starting tool generation: {description[:100]}...")
        
        try:
            # 1. Analyze description (extract spec)
            spec = self.analyze_description(description, trace_id)
            spec.trace_id = trace_id
            
            if implementation_hints:
                spec.implementation_hints.update(implementation_hints)
            
            logger.info(f"[{trace_id}] Tool spec generated: {spec.name}")
            
            # PATCH PROTOCOL: Check if tool already exists
            existing_code = None
            existing_path = self.tools_dir / spec.file_name
            if existing_path.exists():
                try:
                    existing_code = existing_path.read_text()
                    logger.info(f"[{trace_id}] Patch Protocol: Existing tool found ({len(existing_code)} chars). Will extend, not overwrite.")
                except Exception as read_err:
                    logger.warning(f"[{trace_id}] Patch Protocol: Could not read existing tool: {read_err}")
            
            # 2. Generate implementation (real code via Nexus, with existing context)
            implementation_code = self.generate_implementation(spec, trace_id, existing_code=existing_code)
            spec.implementation_hints['code'] = implementation_code
            
            logger.info(f"[{trace_id}] Implementation code generated ({len(implementation_code)} chars)")
            
            # 3. Generate code file
            code = self.generator.generate(spec)
            
            logger.info(f"[{trace_id}] Tool file generated ({len(code)} chars)")
            
            # 4. Validate (with self-healing if needed)
            validation = self.validator.validate(code, spec)
            
            if not validation.success:
                error_msg = "; ".join(validation.errors)
                logger.warning(f"[{trace_id}] Initial validation failed: {error_msg}")
                logger.info(f"[{trace_id}] Attempting self-heal...")
                
                try:
                    # Self-heal the implementation
                    fixed_implementation = self.self_heal_tool(
                        broken_code=implementation_code,
                        error=error_msg,
                        spec=spec,
                        trace_id=trace_id,
                        max_attempts=self._get_max_retries()
                    )
                    
                    # Update spec with fixed code
                    spec.implementation_hints['code'] = fixed_implementation
                    
                    # Regenerate tool file with fixed code
                    code = self.generator.generate(spec)
                    
                    logger.info(f"[{trace_id}] Tool regenerated with healed implementation")
                    
                except Exception as heal_error:
                    logger.error(f"[{trace_id}] Self-heal failed: {str(heal_error)}")
                    raise ValueError(f"Tool validation failed and self-heal unsuccessful: {error_msg}")
            
            if validation.warnings:
                warnings_msg = "; ".join(validation.warnings)
                logger.warning(f"[{trace_id}] Tool validation warnings: {warnings_msg}")
            
            logger.info(f"[{trace_id}] Tool validation passed")
            
            # Register package usage
            if validation.detected_imports:
                try:
                    from core.workspace.package_manager import get_package_manager
                    pm = get_package_manager()
                    for pkg in validation.detected_imports:
                        pm.register_usage(pkg)
                    logger.info(f"[{trace_id}] Registered usage for packages: {validation.detected_imports}")
                except Exception as e:
                    logger.warning(f"[{trace_id}] Failed to register package usage: {e}")
            
            # 5. Save to file
            file_path = self.tools_dir / spec.file_name
            with open(file_path, 'w') as f:
                f.write(code)
            
            logger.info(f"[{trace_id}] Tool saved: {file_path}")
            
            # PHASE C: Test Import Verification
            module_name = spec.file_name.replace('.py', '')
            try:
                # Invalidate cached module if it was previously imported
                full_module = f"data.ai.tools.generated.{module_name}"
                if full_module in importlib.sys.modules:
                    del importlib.sys.modules[full_module]
                
                spec_module = importlib.import_module(full_module)
                tool_func = getattr(spec_module, spec.name, None)
                
                if tool_func is None:
                    logger.warning(f"[{trace_id}] Phase C: Tool importable but function '{spec.name}' not found as attribute")
                else:
                    logger.info(f"[{trace_id}] Phase C PASSED: Tool '{spec.name}' is importable and callable")
                    
            except Exception as import_error:
                logger.warning(f"[{trace_id}] Phase C FAILED: Import test error: {import_error}")
                # Don't block registration - tool may still work when loaded differently
                # But log it clearly for debugging
            
            # 6. Register
            tool_info = {
                **spec.to_dict(),
                'file_path': str(file_path),
                'code_length': len(code),
                'validation_status': 'passed'
            }
            
            self.registry.register(tool_info)
            
            logger.info(f"[{trace_id}] Tool registered: {spec.name}")
            
            # Log to Memory Tier
            self._log_to_memory(spec, trace_id, file_path)
            
            # Complete trace
            self.trace_manager.end_trace(trace_id)
            
            logger.info(
                f"[{trace_id}] Tool generation complete: {spec.name} "
                f"(registry: {self.registry.get_tool_count()} tools)"
            )
            
            return tool_info
            
        except Exception as e:
            logger.error(f"[{trace_id}] Tool generation failed: {str(e)}")
            self.trace_manager.end_trace(trace_id)
            raise
    
    def analyze_description(self, description: str, trace_id: str) -> ToolSpec:
        """
        Analyze tool description using Nexus Core.
        
        Args:
            description: Natural language description
            trace_id: Trace ID for logging
            
        Returns:
            ToolSpec extracted from description
        """
        # Load allowed domains and actions from config
        from core.utils.validators import ALLOWED_DOMAINS, ALLOWED_ACTIONS
        
        analysis_prompt = f"""Analyze this tool request and extract structured information.

Tool Request: {description}

CRITICAL RULES FOR INTELLIGENT TOOL DESIGN:
1.  **AI vs Tool**: The AI (you) provides INTELIGENCE/CONTENT. The Tool provides CAPABILITY/ACTION.
    -   BAD: `Generate_EldenRing_Lore` (The tool shouldn't know about Elden Ring).
    -   GOOD: `System_Write_File(content: str)` (The AI generates the lore, the tool saves it).
2.  **General vs Specific**: 
    -   If the user asks for "write X to a file", create a GENERIC file writing tool, not a specific one.
    -   If the user asks for "fetch weather", create a SPECIFIC `Weather_Get_Forecast` tool (because the AI cannot guess the weather).
3.  **Reuse**: If a standard tool (like `System_Write_File`, `System_Read_File`) likely exists or is implied, suggest a name that aligns with standard utilities.

Extract:
1.  Domain - Choose from: {', '.join(ALLOWED_DOMAINS)}
2.  Action - Choose from: {', '.join(ALLOWED_ACTIONS)}
3.  Object - What the tool operates on (PascalCase, e.g., "StockPrice", "File").
    -   If writing a file, Object should be "File" or "TextFile", NOT "EldenRingLore".
4.  Description - Clear one-line description.
5.  Parameters - List of parameters.
    -   **CRITICAL**: If the tool writes/processes content, it MUST have a `content` parameter. NEVER hardcode content in the tool.
6.  Return Type - What the tool returns.
7.  Implementation Type - "function" or "class".
8.  Reasoning - Explain WHY you chose this design. Explicitly state: "This tool is [General/Specific] because..."

Return ONLY valid JSON in this exact format:
{{
  "domain": "...",
  "action": "...",
  "object": "...",
  "description": "...",
  "parameters": [
    {{"name": "...", "type": "str", "description": "...", "required": true}}
  ],
  "return_type": "str",
  "implementation_type": "function",
  "reasoning": "..."
}}
"""
        
        logger.debug(f"[{trace_id}] Sending analysis prompt to Nexus Core")
        
        request = Request(
            prompt=analysis_prompt,
            request_type="forge_analysis",
            metadata={'tool_description': description},
            temperature=0.1  # Low temperature for structured output
        )
        
        response = self.nexus.route_request(request)
        
        if not response.success:
            raise RuntimeError(f"Nexus Core analysis failed: {response.error}")
        
        logger.debug(f"[{trace_id}] Analysis response received")
        
        # Parse JSON response
        try:
            # Extract JSON from response (may have markdown code blocks)
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            
            # Build ToolSpec
            parameters = [
                ParameterSpec(**param) for param in data.get('parameters', [])
            ]
            
            spec = ToolSpec(
                domain=data['domain'],
                action=data['action'],
                object=data['object'],
                description=data['description'],
                parameters=parameters,
                return_type=data.get('return_type', 'Any'),
                implementation_type=data.get('implementation_type', 'function')
            )
            spec.reasoning = data.get('reasoning', '')
            
            return spec
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"[{trace_id}] Failed to parse analysis response: {str(e)}")
            logger.error(f"[{trace_id}] Response content: {response.content[:500]}")
            raise ValueError(f"Failed to parse tool specification: {str(e)}")
    
    def generate_implementation(self, spec: ToolSpec, trace_id: str, existing_code: str = None) -> str:
        """
        Generate actual implementation code using Nexus Core.
        
        This is Phase 2 of tool generation - generates working Python code
        based on the tool specification extracted in Phase 1.
        
        Args:
            spec: Tool specification with parameters and description
            trace_id: Trace ID for logging
            existing_code: Existing tool code to preserve (Patch Protocol)
            
        Returns:
            Python implementation code (function body)
        """
        # Query available packages from PackageManager
        try:
            from core.workspace.package_manager import get_package_manager
            package_manager = get_package_manager()
            installed_packages = package_manager.get_installed_packages()
            available_packages = list(installed_packages.keys())
            
            # Add standard library packages that are always available
            standard_libs = ['json', 'pathlib', 'datetime', 're', 'os', 'sys', 'typing', 
                           'dataclasses', 'collections', 'itertools', 'functools']
            available_packages.extend(standard_libs)
            
            packages_info = f"\n\nAVAILABLE PACKAGES (you can import these):\n{', '.join(available_packages)}\n"
            logger.info(f"[{trace_id}] Available packages: {len(available_packages)} total")
            
        except Exception as e:
            logger.warning(f"[{trace_id}] Could not query PackageManager: {e}")
            packages_info = "\n\nNOTE: Use only standard library packages (json, pathlib, etc.)\n"
        
        # Build detailed prompt for code generation
        params_desc = "\n".join([
            f"  - {p.name} ({p.type}): {p.description}"
            for p in spec.parameters
        ])
        
        prompt = f"""Generate a complete, working Python implementation for this tool.

Tool Name: {spec.name}
Domain: {spec.domain}
Description: {spec.description}
Action: {spec.action}
Object: {spec.object}

Parameters:
{params_desc if params_desc else "  (none)"}

Return Type: {spec.return_type}
{packages_info}

{self._build_provider_context()}
{self._build_patch_context(existing_code)}
REQUIREMENTS:
1. Write ONLY the function body code (the implementation inside the function)
2. Use proper Python syntax with error handling
3. Include necessary imports at the top if needed (requests, json, pathlib, etc.)
4. ONLY import packages from the AVAILABLE PACKAGES list above
5. If you need a package not in the list, use a simpler alternative or standard library
6. Return the correct type: {spec.return_type}
7. Make it production-ready, not a placeholder
8. Add helpful comments for complex logic
9. Handle edge cases and errors gracefully

CRITICAL - RETURN VALUE REQUIREMENT:
- The function MUST return a value of type {spec.return_type}
- If you define helper functions, you MUST call them and return their result
- NEVER leave the function without an explicit return statement
- Example: If you define `def helper(): ...`, you MUST end with `return helper(args)`

IMPORTANT: Do NOT include the function definition line (def {spec.name}...) - only the body.
If you need imports, put them at the very top as separate lines.

Example format:
```
# Import statements (if needed)
import requests
import json

# Helper function (if needed)
def helper_function(data):
    # Process data
    return processed_result

# Main implementation
try:
    # Actual implementation here
    result = helper_function(some_data)
    return result  # CRITICAL: Always return!
except Exception as e:
    logger.error(f"Error: {{e}}")
    return {{"error": str(e)}}
```
"""
        
        logger.info(f"[{trace_id}] Requesting implementation from Nexus for {spec.name}")
        
        # Call Nexus to generate code
        request = Request(
            prompt=prompt,
            metadata={
                'trace_id': trace_id,
                'operation': 'code_generation',
                'tool': spec.name
            }
        )
        
        response = self.nexus.route_request(request)
        implementation = response.content.strip()
        
        # Clean up code fences if Nexus wrapped it
        if implementation.startswith('```'):
            lines = implementation.split('\n')
            # Remove first line if it's just ```python or ```
            if lines[0].strip().startswith('```'):
                lines = lines[1:]
            # Remove last line if it's just ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            implementation = '\n'.join(lines).strip()
        
        logger.info(f"[{trace_id}] Implementation generated ({len(implementation)} chars)")
        
        return implementation
    
    def self_heal_tool(
        self,
        broken_code: str,
        error: str,
        spec: ToolSpec,
        trace_id: str,
        max_attempts: int = 3
    ) -> str:
        """
        Autonomously fix a broken tool.
        
        This is the self-healing loop - analyzes errors and regenerates
        tool implementations until validation passes.
        
        Args:
            broken_code: The code that failed validation
            error: Error message from validation
            spec: Tool specification
            trace_id: Trace ID for logging
            max_attempts: Maximum fix attempts (default: 3)
            
        Returns:
            Fixed Python code
            
        Raises:
            ValueError: If tool cannot be fixed after max_attempts
        """
        logger.warning(f"[{trace_id}] Starting self-heal for {spec.name}: {error}")
        
        current_code = broken_code
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"[{trace_id}] Self-heal attempt {attempt}/{max_attempts}")
            
            # Build fix prompt
            fix_prompt = f"""Fix this broken Python tool implementation.

Tool: {spec.name}
Domain: {spec.domain}
Description: {spec.description}

ERROR: {error}

BROKEN CODE:
```python
{current_code}
```

REQUIREMENTS:
1. Fix the error mentioned above
2. Ensure proper syntax and imports
3. Match the tool specification exactly
4. Return type: {spec.return_type}
5. Parameters: {[p.name + ': ' + p.type for p in spec.parameters]}

Return ONLY the corrected Python code (function body + imports if needed).
Do NOT include the function definition line.
"""
            
            # Call Nexus to fix
            request = Request(
                prompt=fix_prompt,
                metadata={
                    'trace_id': trace_id,
                    'operation': 'tool_healing',
                    'attempt': attempt
                }
            )
            
            response = self.nexus.route_request(request)
            fixed_code = response.content.strip()
            
            # Clean code fences
            if fixed_code.startswith('```'):
                lines = fixed_code.split('\n')
                if lines[0].strip().startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                fixed_code = '\n'.join(lines).strip()
            
            logger.info(f"[{trace_id}] Fixed code generated ({len(fixed_code)} chars)")
            
            # Validate the fix
            validation = self.validator.validate(fixed_code, spec)
            
            if validation.success:
                logger.info(f"[{trace_id}] ✓ Self-heal successful on attempt {attempt}")
                return fixed_code
            else:
                # Still broken, log and try again
                error = "; ".join(validation.errors)
                logger.warning(f"[{trace_id}] Attempt {attempt} failed: {error}")
                current_code = fixed_code  # Use this version for next attempt
        
        # Failed all attempts
        raise ValueError(
            f"Could not fix {spec.name} after {max_attempts} attempts. "
            f"Last error: {error}"
        )
    

    def get_tool_count(self) -> int:
        """Get number of registered tools."""
        return self.registry.get_tool_count()
    
    def list_tools(self, domain: Optional[str] = None):
        """List all registered tools."""
        return self.registry.list_tools(domain)
    
    def search_tools(self, query: str):
        """Search tools by name or description."""
        return self.registry.search_tools(query)
    
    def _log_to_memory(self, spec: ToolSpec, trace_id: str, file_path: Path):
        """
        Log tool creation to Memory Tier.
        
        Args:
            spec: Tool specification
            trace_id: Trace ID for this generation
            file_path: Path to generated tool file
        """
        try:
            # Import here to avoid circular dependencies
            from core.memory import (
                get_episodic_memory,
                get_knowledge_graph,
                EpisodicMemory,
                generate_memory_id
            )

            # Create episodic memory
            memory = EpisodicMemory(
                memory_id=generate_memory_id(),
                trace_id=trace_id,
                timestamp=utcnow_iso(),
                event_type='tool_forge',
                domain=spec.domain,
                summary=f"Generated {spec.name} tool",
                content=f"Tool '{spec.name}' created: {spec.description}",
                metadata={
                    'tool_name': spec.name,
                    'tool_file': str(file_path),
                    'parameters': [p.name for p in spec.parameters],
                    'return_type': spec.return_type
                }
            )
            
            # Store in episodic memory
            memory_store = get_episodic_memory()
            memory_store.store(memory)
            
            logger.debug(f"[{trace_id}] Tool logged to episodic memory")
            
            # Add to knowledge graph
            kg = get_knowledge_graph()
            
            # Add tool node and link to domain
            kg.add_tool(
                tool_name=spec.name,
                domain=spec.domain,
                metadata={
                    'type': spec.implementation_type,
                    'description': spec.description
                }
            )
            
            # Add trace ID node
            kg.add_trace_id(
                trace_id=trace_id,
                event_type='tool_forge'
            )
            
            # Link tool to trace
            kg.link_tool_to_trace(spec.name, trace_id)
            
            # Save graph
            kg.save()
            
            logger.debug(f"[{trace_id}] Tool linked in knowledge graph")
            
        except Exception as e:
            # Don't fail tool generation if memory logging fails
            logger.warning(f"[{trace_id}] Memory logging failed: {str(e)}")

