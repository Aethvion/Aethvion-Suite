"""
Misaka Cipher - Discord Persistent Worker
Persistent background service for real-time Discord communication.
"""

import asyncio
import discord
from discord.ext import commands
from typing import Optional, Dict, Any, List
from datetime import datetime

from core.utils import get_logger, generate_trace_id
from core.orchestrator.task_models import Task, TaskStatus
from core.memory.social_registry import get_social_registry
from core.security import IntelligenceFirewall, RoutingDecision

from core.memory.history_manager import HistoryManager
import mimetypes

logger = get_logger(__name__)

class DiscordWorker(commands.Bot):
    """
    Discord Persistent Worker - Long-running service for Discord.
    
    Responsibilities:
    - Maintain single persistent gateway connection.
    - Inbound: Map Users -> Registry, Scan Firewall -> Orchestrator.
    - Outbound: Poll Task Queue for 'DISCORD_SEND' actions.
    - Mirroring: Log all Discord messages to unified history.
    - Proactive: Initiate conversations based on memory and scheduler.
    """
    
    def __init__(self, orchestrator, task_manager, bot_token: str):
        """
        Initialize Discord Worker.
        
        Args:
            orchestrator: MasterOrchestrator instance
            task_manager: TaskQueueManager instance
            bot_token: Discord Bot Token
        """
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # For Social Registry info
        
        super().__init__(command_prefix="!", intents=intents)
        
        self.orchestrator = orchestrator
        self.task_manager = task_manager
        self.bot_token = bot_token
        self.registry = get_social_registry()
        self.firewall = IntelligenceFirewall()
        
        # Load Main User ID from preferences for security
        from core.workspace.preferences_manager import get_preferences_manager
        prefs = get_preferences_manager()
        self.main_user_id = prefs.get('nexus.discord_link.main_user_id')
        
        self.worker_running = False
        self.poll_task = None
        self.proactive_task = None
        
    async def on_ready(self):
        """Called when bot has connected and is ready."""
        logger.info(f"Discord Worker logged in as {self.user} (ID: {self.user.id})")
        
        # Start background tasks
        self.worker_running = True
        self.poll_task = asyncio.create_task(self._poll_task_queue())
        self.proactive_task = asyncio.create_task(self._proactive_loop())
        logger.info("Discord background services started (Polling & Proactive)")

    async def on_message(self, message: discord.Message):
        """Handle inbound messages."""
        # Ignore self
        if message.author == self.user:
            return

        # CONDITIONAL RESPONDING:
        # 1. Direct Messages (DMs)
        # 2. Mentions in a server
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_main_user = str(message.author.id) == str(self.main_user_id)
        is_mention = self.user.mentioned_in(message)
        
        if not (is_dm or is_mention):
            # Still log it if it's in a server we are in? No, only log what Misaka "sees" or cares about.
            # Mirroring says "all Discord communications (both sent and received)".
            # Let's mirror what involves her.
            return

        # Map user to social registry
        profile = self.registry.map_user(
            platform="discord",
            platform_id=str(message.author.id),
            name=message.author.display_name,
            metadata={
                "tag": str(message.author),
                "is_bot": message.author.bot,
                "roles": [r.name for r in message.author.roles] if hasattr(message.author, 'roles') else []
            }
        )
        
        trace_id = generate_trace_id()
        logger.info(f"[{trace_id}] Discord Inbound: From {profile['display_name']} in {message.channel}")

        # Mirror User message to unified history ONLY if it's an authorized DM
        if is_dm and is_main_user:
            HistoryManager.log_message(
                role="user",
                content=message.content,
                platform="discord",
                metadata={
                    "discord_user_id": str(message.author.id),
                    "channel_id": str(message.channel.id),
                    "is_dm": is_dm
                }
            )

        # Context injection for Misaka
        prompt = f"Context: USER={profile['display_name']} (ID: {profile['internal_id']})\n\nMessage: {message.content}"

        # 1. Intelligence Firewall Scan (Inbound)
        routing_decision, scan_result = self.firewall.scan_and_route(prompt, trace_id)
        
        if routing_decision == RoutingDecision.BLOCKED:
            logger.warning(f"[{trace_id}] Inbound Discord message BLOCKED by firewall")
            await message.reply("⚠️ [Intelligence Firewall] Message blocked due to security restrictions.")
            return

        # 2. Process via Master Orchestrator
        loop = asyncio.get_event_loop()
        try:
            # Shared Context: Load recent history for Misaka to "remember" previous turns
            history = HistoryManager.get_recent_history(limit=10)
            context_lines = []
            for h in history:
                role = "Misaka" if h["role"] == "assistant" else "User"
                context_lines.append(f"{role}: {h['content']}")
            
            history_context = "\n".join(context_lines) if context_lines else "No previous conversation history."
            
            # Security: Allow sensitive tasks ONLY for the main user in DM
            security_context = ""
            allow_tools = False
            
            if is_dm and is_main_user:
                security_context = "\nSECURITY NOTICE: This is a Direct Message with the AUTHORIZED MAIN USER. Sensitive tools/tasks are ALLOWED."
                allow_tools = True
            elif is_dm:
                security_context = "\nSECURITY NOTICE: This is a DM with an UNKNOWN user. Administrative tasks and tools are strictly forbidden."
            else:
                security_context = "\nSECURITY NOTICE: This is a public Discord server. You DO NOT have access to tools. Respond conversationally."
            
            full_prompt = f"SHARED CONVERSATION HISTORY:\n---\n{history_context}\n---\n\n{prompt}"

            result = await loop.run_in_executor(
                None,
                lambda: self.orchestrator.process_message(
                    full_prompt, 
                    trace_id=trace_id,
                    source="discord",
                    security_context=security_context,
                    allow_tools=allow_tools
                )
            )
            
            if result.success and result.response:
                # 3. Intelligence Firewall Scan (Outbound)
                out_decision, out_scan = self.firewall.scan_and_route(result.response, trace_id)
                
                if out_decision == RoutingDecision.BLOCKED:
                    logger.warning(f"[{trace_id}] Outbound Discord response BLOCKED by firewall")
                    await message.reply("⚠️ [Intelligence Firewall] My response was blocked due to its sensitive content.")
                else:
                    # Reply to the user
                    response_text = result.response
                    # Strip any internal tags if they leaked
                    import re
                    response_text = re.sub(r'\[Mood:\s*\w+\]?', '', response_text, flags=re.IGNORECASE)
                    response_text = re.sub(r'\[Emotion:\s*\w+\]?', '', response_text, flags=re.IGNORECASE).strip()
                    
                    files = []
                    if getattr(result, "media_paths", None):
                        for m_path in result.media_paths:
                            try:
                                files.append(discord.File(m_path))
                            except Exception as fe:
                                logger.error(f"[{trace_id}] Failed to attach file {m_path}: {fe}")
                                
                    await message.reply(response_text, files=files if files else None)

                    # Mirror Assistant response to unified history ONLY if it's an authorized DM
                    if is_dm and is_main_user:
                        HistoryManager.log_message(
                            role="assistant",
                            content=response_text,
                            platform="discord",
                            metadata={
                                "discord_user_id": str(message.author.id),
                                "channel_id": str(message.channel.id),
                                "trace_id": trace_id
                            }
                        )
            elif not result.success:
                logger.error(f"[{trace_id}] Orchestrator failed to process Discord message: {result.error}")
                
        except Exception as e:
            logger.error(f"[{trace_id}] Error in Discord inbound handler: {e}")

    async def _poll_task_queue(self):
        """Internal loop to poll for DISCORD_SEND tasks."""
        while self.worker_running:
            try:
                for task_id, task in list(self.task_manager.tasks.items()):
                    if task.status == TaskStatus.QUEUED and task.metadata.get('task_type') == 'DISCORD_SEND':
                        await self._execute_discord_task(task)
                
                await asyncio.sleep(2) 
            except Exception as e:
                logger.error(f"Error in Discord poll loop: {e}")
                await asyncio.sleep(5)

    async def _execute_discord_task(self, task: Task):
        """Execute a DISCORD_SEND task."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        channel_id = task.metadata.get('channel_id')
        content = task.prompt 
        trace_id = task.id

        logger.info(f"[{trace_id}] Executing DISCORD_SEND to channel {channel_id}")

        try:
            if not channel_id:
                raise ValueError("No channel_id provided in task metadata")

            out_decision, out_scan = self.firewall.scan_and_route(content, trace_id)
            if out_decision == RoutingDecision.BLOCKED:
                task.status = TaskStatus.FAILED
                task.error = "Blocked by Intelligence Firewall"
            else:
                channel = await self.fetch_channel(int(channel_id))
                if channel:
                    # Check for specialized task results (like SCREENSHOT)
                    # Screenshot tasks in nexus usually save to a path and return it.
                    # We can check if the task prompt or result contains a path to an image.
                    
                    file_to_send = None
                    if task.metadata.get('is_multimodal') and task.metadata.get('media_path'):
                        media_path = task.metadata.get('media_path')
                        if os.path.exists(media_path):
                            file_to_send = discord.File(media_path)
                    
                    if file_to_send:
                        await channel.send(content, file=file_to_send)
                    else:
                        await channel.send(content)
                        
                    task.status = TaskStatus.COMPLETED
                    task.result = {"success": True, "channel_id": channel_id}
                    
                    # Mirror outbound messages from Dashboard to Discord
                    HistoryManager.log_message(
                        role="assistant",
                        content=content,
                        platform="discord",
                        attachments=[{"url": task.metadata.get('media_url')}] if task.metadata.get('media_url') else None,
                        metadata={"channel_id": channel_id, "task_id": task_id}
                    )
                else:
                    raise ValueError(f"Could not find channel with ID {channel_id}")

        except Exception as e:
            logger.error(f"[{trace_id}] Discord Task Failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
        
        task.completed_at = datetime.now()
        if hasattr(self.task_manager, '_save_task'):
            self.task_manager._save_task(task)

    async def _proactive_loop(self):
        """
        Background loop for proactive messaging.
        Misaka can decide to "wake up" and send DMs to the user.
        """
        logger.info("Misaka proactive DM module engaged.")
        
        # Initial wait to let system settle
        await asyncio.sleep(60)
        
        while self.worker_running:
            try:
                # Logic: Is it a good time to talk?
                # Check memory for user preferences or recent events.
                # Use a lightweight "should I talk?" check.
                
                # For now, let's implement a "Neural Pulse" every 1-4 hours
                import random
                wait_minutes = random.randint(60, 240)
                await asyncio.sleep(wait_minutes * 60)
                
                if not self.worker_running: break
                
                logger.info("Neural Pulse: Misaka considering proactive DM...")
                
                # Check if we have a primary user DM channel
                # We can store the last DM channel ID in memory or search for DMs with the owner.
                # For this demo, we'll try to find a DM channel with a known 'User' if configured.
                
                # TODO: Implement actual 'should I reach out?' logic via orchestrator
                # For now, we just log the opportunity.
                
            except Exception as e:
                logger.error(f"Error in proactive loop: {e}")
                await asyncio.sleep(300)

    async def run_worker(self):
        """Main entry point to start the bot."""
        try:
            async with self:
                await self.start(self.bot_token)
        except discord.errors.PrivilegedIntentsRequired:
            logger.error("❌ Privileged Intents Required: Please enable 'MESSAGE CONTENT INTENT' and 'SERVER MEMBERS INTENT' in the Discord Developer Portal.")
            raise
        except Exception as e:
            logger.error(f"❌ Discord Worker failed to start: {e}")
            raise

    def stop_worker(self):
        """Stop the worker gracefully."""
        self.worker_running = False
        if self.poll_task:
            self.poll_task.cancel()
        if self.proactive_task:
            self.proactive_task.cancel()
        asyncio.create_task(self.close())

def start_discord_service(orchestrator, task_manager, bot_token: str):
    """Bridge for starting the service from a sync context if needed."""
    worker = DiscordWorker(orchestrator, task_manager, bot_token)
    return worker
