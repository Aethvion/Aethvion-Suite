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

logger = get_logger(__name__)

class DiscordWorker(commands.Bot):
    """
    Discord Persistent Worker - Long-running service for Discord.
    
    Responsibilities:
    - Maintain single persistent gateway connection.
    - Inbound: Map Users -> Registry, Scan Firewall -> Orchestrator.
    - Outbound: Poll Task Queue for 'DISCORD_SEND' actions.
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
        
        self.worker_running = False
        self.poll_task = None
        
    async def on_ready(self):
        """Called when bot has connected and is ready."""
        logger.info(f"Discord Worker logged in as {self.user} (ID: {self.user.id})")
        
        # Start the task queue poll loop
        self.worker_running = True
        self.poll_task = asyncio.create_task(self._poll_task_queue())
        logger.info("Discord Task Queue polling started")

    async def on_message(self, message: discord.Message):
        """Handle inbound messages."""
        # Ignore self
        if message.author == self.user:
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

        # Social/Context injection: Prepend user context to prompt
        # So the orchestrator knows who it is talking to.
        prompt = f"Context: USER={profile['display_name']} (ID: {profile['internal_id']})\n\nMessage: {message.content}"

        # 1. Intelligence Firewall Scan (Inbound)
        routing_decision, scan_result = self.firewall.scan_and_route(prompt, trace_id)
        
        if routing_decision == RoutingDecision.BLOCKED:
            logger.warning(f"[{trace_id}] Inbound Discord message BLOCKED by firewall")
            await message.reply("⚠️ [Intelligence Firewall] Message blocked due to security restrictions.")
            return

        # 2. Process via Master Orchestrator
        # Since orchestrator is sync, we run in executor
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self.orchestrator.process_message(prompt, trace_id=trace_id)
            )
            
            if result.success and result.response:
                # 3. Intelligence Firewall Scan (Outbound)
                out_decision, out_scan = self.firewall.scan_and_route(result.response, trace_id)
                
                if out_decision == RoutingDecision.BLOCKED:
                    logger.warning(f"[{trace_id}] Outbound Discord response BLOCKED by firewall")
                    await message.reply("⚠️ [Intelligence Firewall] My response was blocked due to its sensitive content.")
                else:
                    # Reply to the user
                    await message.reply(result.response)
            elif not result.success:
                logger.error(f"[{trace_id}] Orchestrator failed to process Discord message: {result.error}")
                
        except Exception as e:
            logger.error(f"[{trace_id}] Error in Discord inbound handler: {e}")

    async def _poll_task_queue(self):
        """Internal loop to poll for DISCORD_SEND tasks."""
        logger.info("Discord Worker poll loop active")
        while self.worker_running:
            try:
                # Find tasks in the queue manager that are QUEUED and type DISCORD_SEND
                # Task types aren't explicitly in task_models yet, but we'll use metadata
                for task_id, task in list(self.task_manager.tasks.items()):
                    if task.status == TaskStatus.QUEUED and task.metadata.get('task_type') == 'DISCORD_SEND':
                        await self._execute_discord_task(task)
                
                await asyncio.sleep(2) # Poll every 2 seconds
            except Exception as e:
                logger.error(f"Error in Discord poll loop: {e}")
                await asyncio.sleep(5)

    async def _execute_discord_task(self, task: Task):
        """Execute a DISCORD_SEND task."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        channel_id = task.metadata.get('channel_id')
        content = task.prompt # For outgoing, prompt is the content
        trace_id = task.id

        logger.info(f"[{trace_id}] Executing DISCORD_SEND to channel {channel_id}")

        try:
            if not channel_id:
                raise ValueError("No channel_id provided in task metadata")

            # Firewall Scan (Outbound Task)
            out_decision, out_scan = self.firewall.scan_and_route(content, trace_id)
            if out_decision == RoutingDecision.BLOCKED:
                task.status = TaskStatus.FAILED
                task.error = "Blocked by Intelligence Firewall"
                logger.warning(f"[{trace_id}] Outbound Task BLOCKED")
            else:
                channel = await self.fetch_channel(int(channel_id))
                if channel:
                    await channel.send(content)
                    task.status = TaskStatus.COMPLETED
                    task.result = {"success": True, "channel_id": channel_id}
                else:
                    raise ValueError(f"Could not find channel with ID {channel_id}")

        except Exception as e:
            logger.error(f"[{trace_id}] Discord Task Failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)
        
        task.completed_at = datetime.now()
        # Persist task update via task manager if possible (private method)
        if hasattr(self.task_manager, '_save_task'):
            self.task_manager._save_task(task)

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
        asyncio.create_task(self.close())

def start_discord_service(orchestrator, task_manager, bot_token: str):
    """Bridge for starting the service from a sync context if needed."""
    worker = DiscordWorker(orchestrator, task_manager, bot_token)
    return worker
