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
    from core.companions.registry import CompanionRegistry

    while True:
        clear_screen()
        print_header("Companions", "AI Companion Registry & Memory")

        companion_list = CompanionRegistry.list_companions()

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


# Companion detail menu

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


# Sub-views

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
    """Show interactive JSON memory."""
    clear_screen()
    print_header(f"{companion.name} — Memory", "Dynamic behavior state (memory.json)")

    memory_file = companion.data_dir / "memory.json"
    if not memory_file.exists():
        print_warning("No memory file found.")
    else:
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            console.print(json.dumps(data, indent=4))
        except Exception as e:
            print_error(f"Error reading memory: {e}")

    pause()

def _show_companion_base_info(companion):
    """Show character core identity."""
    clear_screen()
    print_header(f"{companion.name} — Base Info", "Personality Blueprints (base_info.json)")

    base_file = companion.data_dir / "base_info.json"
    if not base_file.exists():
        print_warning("No base_info file found.")
    else:
        try:
            with open(base_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            console.print(json.dumps(data, indent=4))
        except Exception as e:
            print_error(f"Error reading base_info: {e}")

    pause()

def _show_companion_history_stats(companion):
    """Show counts per platform."""
    clear_screen()
    print_header(f"{companion.name} — History Stats", "Message metrics")

    hist_dir = companion.history_dir
    if not hist_dir.exists():
        print_warning("No history directory found.")
    else:
        try:
            days = list(hist_dir.glob("*.json"))
            console.print(f"  Active Days: {len(days)}")
            
            total_msgs = 0
            for d_file in days:
                with open(d_file, "r", encoding="utf-8") as f:
                    day_data = json.load(f)
                    total_msgs += len(day_data.get("messages", []))
            
            console.print(f"  Total Messages: {total_msgs}")
        except Exception as e:
            print_error(f"Error calculating stats: {e}")

    pause()
