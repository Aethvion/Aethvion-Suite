"""
Aethvion Suite - Companions Module
CLI module for viewing companion registry, memory, and history stats
"""

import json
from pathlib import Path
from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    print_key_value, print_warning, print_error, print_success, pause
)


def companions_module():
    """Main entry point for Companions CLI module."""
    from core.companions.registry import COMPANIONS

    while True:
        clear_screen()
        print_header("Companions", "AI Companion Registry & Memory")

        companion_list = list(COMPANIONS.values())

        if not companion_list:
            print_warning("No companions registered in registry.")
            pause()
            return

        options = []
        for c in companion_list:
            desc = c.description[:55] + "…" if len(c.description) > 55 else c.description
            options.append(f"{c.name:<20} — {desc}")

        print_menu("Registered Companions", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break

        _show_companion_detail(companion_list[choice - 1])


# ── Companion detail menu ──────────────────────────────────────────────────────

def _show_companion_detail(companion):
    """Drill-down menu for a single companion."""
    while True:
        clear_screen()
        print_header(companion.name, companion.description)

        options = [
            "View Config         — Registry settings & file paths",
            "View Memory         — Dynamic memory  (memory.json)",
            "View Base Info      — Personality & identity (base_info.json)",
            "Chat History Stats  — Message count summary",
        ]
        print_menu(f"{companion.name}", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break
        elif choice == 1:
            _show_companion_config(companion)
        elif choice == 2:
            _show_companion_memory(companion)
        elif choice == 3:
            _show_companion_base_info(companion)
        elif choice == 4:
            _show_companion_history_stats(companion)


# ── Sub-views ─────────────────────────────────────────────────────────────────

def _show_companion_config(companion):
    """Show companion registry configuration and path health."""
    clear_screen()
    print_header(f"{companion.name} — Config", "Registry Settings & Paths")

    print_key_value("ID",                 companion.id)
    print_key_value("Route Prefix",       companion.route_prefix)
    print_key_value("Call Source",        companion.call_source)
    print_key_value("Prefs Key",          companion.prefs_key)
    print_key_value("Default Model",      companion.default_model)
    print_key_value("Default Expression", companion.default_expression)
    print_key_value("Static Dir",         companion.static_dir)
    print_key_value("Data Dir",           str(companion.data_dir))
    print_key_value("History Dir",        str(companion.history_dir))

    data_ok    = "[green]✓ exists[/green]"    if companion.data_dir.exists()    else "[red]✗ missing[/red]"
    history_ok = "[green]✓ exists[/green]"    if companion.history_dir.exists() else "[red]✗ missing[/red]"
    console.print(f"\n  Data Dir:    {data_ok}")
    console.print(f"  History Dir: {history_ok}")

    console.print(f"\n[bold cyan]Expressions ({len(companion.expressions)}):[/bold cyan]")
    console.print("  " + ", ".join(companion.expressions))

    console.print(f"\n[bold cyan]Moods ({len(companion.moods)}):[/bold cyan]")
    console.print("  " + ", ".join(companion.moods))

    pause()


def _show_companion_memory(companion):
    """Show companion dynamic memory (memory.json)."""
    clear_screen()
    print_header(f"{companion.name} — Memory", "Dynamic Memory (memory.json)")

    memory_file = companion.data_dir / "memory.json"
    if not memory_file.exists():
        print_warning("memory.json does not exist yet.")
        console.print("[dim]Misaka will create it automatically on first chat.[/dim]")
        pause()
        return

    try:
        with open(memory_file) as f:
            data = json.load(f)

        print_key_value("Last Updated", data.get("last_updated", "Unknown"))

        user_info    = data.get("user_info", {})
        observations = data.get("recent_observations", [])

        console.print("\n[bold cyan]User Info:[/bold cyan]")
        if user_info:
            for k, v in user_info.items():
                print_key_value(f"  {k}", v)
        else:
            console.print("  [dim]No user info stored yet.[/dim]")

        console.print(f"\n[bold cyan]Recent Observations ({len(observations)}):[/bold cyan]")
        if observations:
            for i, obs in enumerate(observations[-15:], 1):
                console.print(f"  [dim]{i:>2}.[/dim] {obs}")
        else:
            console.print("  [dim]No observations stored yet.[/dim]")

    except Exception as e:
        print_error(f"Failed to read memory.json: {e}")

    pause()


def _show_companion_base_info(companion):
    """Show companion base identity (base_info.json)."""
    clear_screen()
    print_header(f"{companion.name} — Base Info", "Personality & Identity (base_info.json)")

    base_info_file = companion.data_dir / "base_info.json"
    if not base_info_file.exists():
        print_warning("base_info.json does not exist yet.")
        pause()
        return

    try:
        with open(base_info_file) as f:
            data = json.load(f)
        console.print_json(json.dumps(data, indent=2))
    except Exception as e:
        print_error(f"Failed to read base_info.json: {e}")

    pause()


def _show_companion_history_stats(companion):
    """Show chat history statistics for this companion."""
    clear_screen()
    print_header(f"{companion.name} — History Stats", "Chat History Summary")

    history_dir = companion.history_dir
    if not history_dir.exists():
        print_warning("History directory does not exist yet.")
        pause()
        return

    try:
        history_files  = sorted(history_dir.rglob("chat_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        total_files    = len(history_files)
        total_messages = 0

        for f in history_files:
            try:
                with open(f) as hf:
                    raw = json.load(hf)
                if isinstance(raw, list):
                    total_messages += len(raw)
                elif isinstance(raw, dict) and "messages" in raw:
                    total_messages += len(raw["messages"])
            except Exception:
                pass

        print_key_value("History Files on Disk", total_files)
        print_key_value("Total Messages",         total_messages)

        if history_files:
            console.print("\n[bold cyan]5 Most Recent Files:[/bold cyan]")
            for hf in history_files[:5]:
                console.print(f"  • {hf.name}")

        print_success("Stats loaded")
    except Exception as e:
        print_error(f"Failed to read history: {e}")

    pause()
