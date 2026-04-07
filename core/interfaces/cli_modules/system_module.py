"""
Aethvion Suite - System Status Module
Displays system diagnostics and health information
"""

import os
from pathlib import Path
from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_table,
    print_key_value, print_success, print_warning, print_error, pause
)
from core.nexus_core import NexusCore
from core.factory import AgentFactory
from core.forge import ToolForge
from core.memory import get_episodic_memory, get_knowledge_graph
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def show_system_status(nexus: NexusCore, factory: AgentFactory, forge: ToolForge):
    """
    Display comprehensive system status.

    Args:
        nexus: NexusCore instance
        factory: AgentFactory instance
        forge: ToolForge instance
    """
    clear_screen()
    print_header("System Status", "Aethvion Suite — Comprehensive Diagnostics")

    issues = []  # Track any problems for the health summary

    # ── Nexus Core ──────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ Nexus Core ═══[/bold cyan]")
    status = nexus.get_status()

    print_key_value("Initialized",   "✓ Yes" if status['initialized'] else "✗ No")
    print_key_value("Active Traces", status['active_traces'])

    firewall_enabled = status['firewall'].get('enabled', False)
    firewall_label   = "ACTIVE" if firewall_enabled else "DISABLED"
    firewall_color   = "green" if firewall_enabled else "yellow"
    print_key_value("Firewall", f"[{firewall_color}]{firewall_label}[/{firewall_color}]")

    if not firewall_enabled:
        issues.append("Firewall is disabled")

    # Provider Status
    console.print("\n[bold yellow]Providers:[/bold yellow]")
    healthy_count = 0
    for provider_name, provider_info in status['providers']['providers'].items():
        healthy = provider_info['is_healthy']
        icon = "🟢" if healthy else "🔴"
        if healthy:
            healthy_count += 1
        else:
            issues.append(f"Provider '{provider_name}' is unhealthy")
        console.print(
            f"  {icon} {provider_name}: {provider_info['model']} "
            f"({provider_info['status']})"
        )

    if healthy_count == 0:
        issues.append("No providers are healthy")

    # ── Factory ─────────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ The Factory ═══[/bold cyan]")
    try:
        agents       = factory.registry.get_all_agents()
        agent_count  = len(agents)
        active_count = factory.registry.get_active_count()

        print_key_value("Total Agents (All Time)", agent_count)
        print_key_value("Currently Active",        active_count)
        print_key_value("Max Concurrent",          factory.max_concurrent_agents)
        print_success("Factory operational")
    except Exception as e:
        print_warning(f"Factory status unavailable: {str(e)}")
        issues.append(f"Factory: {str(e)}")

    # ── Forge ────────────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ The Forge ═══[/bold cyan]")
    try:
        tool_count   = forge.get_tool_count()
        recent_tools = forge.list_tools()[-3:] if forge.list_tools() else []

        print_key_value("Total Tools", tool_count)
        if recent_tools:
            console.print("[bold yellow]Recent Tools:[/bold yellow]")
            for tool in recent_tools:
                console.print(f"  • {tool['name']} ({tool['domain']})")
        else:
            console.print("[dim]No tools generated yet[/dim]")
        print_success("Forge operational")
    except Exception as e:
        print_warning(f"Forge status unavailable: {str(e)}")
        issues.append(f"Forge: {str(e)}")

    # ── Memory Tier ──────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ The Memory Tier ═══[/bold cyan]")
    try:
        memory_store = get_episodic_memory()
        kg           = get_knowledge_graph()

        memory_count = memory_store.get_count()
        stats        = kg.get_stats()

        print_key_value("Episodic Memories",       memory_count)
        print_key_value("Knowledge Graph Nodes",   stats['total_nodes'])
        print_key_value("Knowledge Graph Edges",   stats['total_edges'])
        print_key_value("Domains",                 stats['domains'])

        console.print("\n[bold yellow]Node Types:[/bold yellow]")
        for node_type, count in stats['node_types'].items():
            console.print(f"  • {node_type}: {count}")

        print_success("Memory Tier operational")
    except Exception as e:
        print_warning(f"Memory Tier status unavailable: {str(e)}")
        issues.append(f"Memory: {str(e)}")

    # ── Chat History ─────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ Chat History ═══[/bold cyan]")
    try:
        from core.memory.history_manager import HistoryManager
        today_count = HistoryManager.get_total_message_count()
        recent      = HistoryManager.get_recent_history(limit=3)

        print_key_value("Messages Today", today_count)

        if recent:
            last = recent[-1]
            ts   = last.get("timestamp", "?")
            plat = last.get("platform", "?")
            role = last.get("role", "?")
            print_key_value("Last Activity", f"{ts} [{plat}] {role}")
        else:
            console.print("[dim]No recent history[/dim]")

        # Count history files
        history_base = _PROJECT_ROOT / "data" / "memory" / "storage" / "misakacipher" / "chathistory"
        if history_base.exists():
            total_files = sum(1 for _ in history_base.rglob("chat_*.json"))
            print_key_value("History Files on Disk", total_files)

        print_success("History Manager operational")
    except Exception as e:
        print_warning(f"History Manager unavailable: {str(e)}")

    # ── Discord Worker ────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ Discord Worker ═══[/bold cyan]")
    try:
        token = os.environ.get("DISCORD_TOKEN", "").strip()
        if not token:
            # Try .env fallback
            env_file = _PROJECT_ROOT / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("DISCORD_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

        if token:
            masked = token[:6] + "…" + token[-4:] if len(token) > 10 else "***"
            print_key_value("Token",  f"[green]Present[/green] ({masked})")
            print_key_value("Status", "[dim]Managed by server process (not CLI)[/dim]")
        else:
            print_key_value("Token",  "[yellow]Not configured[/yellow]")
            print_key_value("Status", "[dim]Discord integration disabled[/dim]")
            console.print("  [dim]Add DISCORD_TOKEN to .env to enable[/dim]")

        # Social Registry stats
        try:
            from core.memory.social_registry import get_social_registry
            registry = get_social_registry()
            profile_count = len(registry.registry)
            print_key_value("Social Registry Profiles", profile_count)
        except Exception:
            pass

    except Exception as e:
        print_warning(f"Discord status check failed: {str(e)}")

    # ── Companions ───────────────────────────────────────────────────────────
    console.print("\n[bold cyan]═══ Companions ═══[/bold cyan]")
    try:
        from core.companions.registry import COMPANIONS
        if not COMPANIONS:
            console.print("[dim]No companions registered.[/dim]")
        else:
            for cid, cfg in COMPANIONS.items():
                data_ok    = "[green]✓[/green]" if cfg.data_dir.exists()    else "[red]✗[/red]"
                history_ok = "[green]✓[/green]" if cfg.history_dir.exists() else "[red]✗[/red]"
                console.print(
                    f"  [bold yellow]{cfg.name}[/bold yellow]  "
                    f"[dim]{cfg.route_prefix}[/dim]  "
                    f"data:{data_ok}  history:{history_ok}  "
                    f"[dim]{len(cfg.expressions)} expressions[/dim]"
                )
            print_success(f"{len(COMPANIONS)} companion(s) registered")
    except Exception as e:
        print_warning(f"Companion registry unavailable: {str(e)}")
        issues.append(f"Companions: {str(e)}")

    # ── Overall Health ────────────────────────────────────────────────────────
    console.print("\n" + "═" * 50)

    if not issues:
        health_panel = Panel(
            "[bold green]System Status: OPERATIONAL[/bold green]\n"
            "All core modules initialized and healthy.",
            title="Overall Health",
            border_style="green"
        )
    else:
        issue_lines = "\n".join(f"  ⚠ {i}" for i in issues)
        health_panel = Panel(
            f"[bold yellow]System Status: DEGRADED[/bold yellow]\n\n"
            f"[yellow]{issue_lines}[/yellow]",
            title="Overall Health",
            border_style="yellow"
        )

    console.print(health_panel)
    pause()
