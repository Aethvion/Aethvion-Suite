"""
Aethvion Suite - Main CLI Interface
Interactive command-line interface for Aethvion Suite system
"""

import sys
from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_banner, print_menu, get_user_choice,
    print_success, print_error, print_warning
)
from core.interfaces.cli_modules.system_module import show_system_status
from core.interfaces.cli_modules.nexus_module import nexus_core_module
from core.interfaces.cli_modules.factory_module import factory_module
from core.interfaces.cli_modules.forge_module import forge_module
from core.interfaces.cli_modules.memory_module import memory_module
from core.interfaces.cli_modules.companions_module import companions_module

from core.nexus_core import NexusCore
from core.factory import AgentFactory
from core.forge import ToolForge
from core.utils import get_logger

logger = get_logger(__name__)


class MisakaCLI:
    """Main CLI coordinator for Aethvion Suite."""

    def __init__(self):
        """Initialize CLI and system components."""
        self.nexus = None
        self.factory = None
        self.forge = None
        self.running = False

    def initialize(self):
        """Initialize all system components."""
        try:
            console.print("[bold cyan]Initializing Aethvion Suite...[/bold cyan]")

            # Initialize Nexus Core
            console.print("  • Nexus Core...", end="")
            self.nexus = NexusCore()
            self.nexus.initialize()
            console.print(" [bold green]✓[/bold green]")

            # Initialize Factory
            console.print("  • The Factory...", end="")
            self.factory = AgentFactory(self.nexus)
            console.print(" [bold green]✓[/bold green]")

            # Initialize Forge
            console.print("  • The Forge...", end="")
            self.forge = ToolForge(self.nexus)
            console.print(" [bold green]✓[/bold green]")

            # Memory Tier initializes lazily
            console.print("  • The Memory Tier...", end="")
            from core.memory import get_episodic_memory, get_knowledge_graph
            get_episodic_memory()
            get_knowledge_graph()
            console.print(" [bold green]✓[/bold green]")

            # History Manager (optional - does not block startup)
            console.print("  • History Manager...", end="")
            try:
                from core.memory.history_manager import HistoryManager
                count = HistoryManager.get_total_message_count()
                console.print(f" [bold green]✓[/bold green] [dim]({count} messages today)[/dim]")
            except Exception as e:
                console.print(f" [yellow]⚠ unavailable[/yellow]")
                logger.warning(f"HistoryManager not available: {e}")

            # Discord worker status check (informational only)
            console.print("  • Discord Worker...", end="")
            try:
                import os
                token = os.environ.get("DISCORD_TOKEN") or _try_read_env_token()
                if token:
                    console.print(" [bold green]✓[/bold green] [dim](token found)[/dim]")
                else:
                    console.print(" [yellow]–[/yellow] [dim](no token, bot disabled)[/dim]")
            except Exception:
                console.print(" [yellow]–[/yellow] [dim](status unavailable)[/dim]")

            # Companions registry check (informational only)
            console.print("  • Companions...", end="")
            try:
                from core.companions.registry import COMPANIONS
                names = [c.name for c in COMPANIONS.values()]
                console.print(f" [bold green]✓[/bold green] [dim]({len(names)} registered: {', '.join(names)})[/dim]")
            except Exception as e:
                console.print(f" [yellow]⚠ unavailable[/yellow]")
                logger.warning(f"Companion registry not available: {e}")

            console.print("\n[bold green]All systems operational[/bold green]\n")
            return True

        except Exception as e:
            console.print(" [bold red]✗[/bold red]")
            print_error(f"Initialization failed: {str(e)}")
            logger.error(f"CLI initialization failed: {str(e)}")
            return False

    def show_main_menu(self):
        """Display main menu."""
        clear_screen()
        print_banner()

        options = [
            "Nexus Core          — Direct AI Interaction",
            "The Factory         — Agent Spawning & Execution",
            "The Forge           — Autonomous Tool Generation",
            "Memory              — Query & Search State",
            "Chat History        — Browse Unified History",
            "Advanced AI Conv.   — Research Lab",
            "LLM Arena           — Model vs Model Battles",
            "Settings            — Configuration & Providers",
            "System Status       — Diagnostics",
            "Companions          — Registry, Memory & Identity",
        ]

        print_menu("Main Menu", options)
        return get_user_choice(len(options), "Select option")

    def run(self):
        """Run the main CLI loop."""
        self.running = True

        if not self.initialize():
            console.print("\n[bold red]Failed to initialize. Press Enter to exit...[/bold red]")
            input()
            return

        input("\nPress Enter to continue...")

        while self.running:
            choice = self.show_main_menu()

            if choice == 0:
                self.running = False
                clear_screen()
                print_success("Goodbye!")
                break

            elif choice == 1:
                from core.interfaces.cli_modules.nexus_module import nexus_core_module
                nexus_core_module(self.nexus)

            elif choice == 2:
                from core.interfaces.cli_modules.factory_module import factory_module
                factory_module(self.factory)

            elif choice == 3:
                from core.interfaces.cli_modules.forge_module import forge_module
                forge_module(self.forge)

            elif choice == 4:
                from core.interfaces.cli_modules.memory_module import memory_module
                memory_module()

            elif choice == 5:
                from core.interfaces.cli_modules.memory_module import chat_history_module
                chat_history_module()

            elif choice == 6:
                from core.interfaces.cli_modules.research_module import research_module
                research_module(self.nexus)

            elif choice == 7:
                from core.interfaces.cli_modules.arena_module import arena_module
                arena_module(self.nexus)

            elif choice == 8:
                from core.interfaces.cli_modules.settings_module import settings_module
                settings_module()

            elif choice == 9:
                from core.interfaces.cli_modules.system_module import show_system_status
                show_system_status(self.nexus, self.factory, self.forge)

            elif choice == 10:
                from core.interfaces.cli_modules.companions_module import companions_module
                companions_module()


def _try_read_env_token() -> str:
    """Try to read DISCORD_TOKEN from .env file as fallback."""
    try:
        from pathlib import Path
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DISCORD_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def main():
    """Main entry point for CLI."""
    try:
        cli = MisakaCLI()
        cli.run()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        print_error(f"Fatal error: {str(e)}")
        logger.error(f"CLI fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
