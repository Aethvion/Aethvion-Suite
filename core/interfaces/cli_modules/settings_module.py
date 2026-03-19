"""
Misaka Cipher - Settings Module
CLI module for managing providers, identity, and social registry
"""

import json
from pathlib import Path
from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    print_success, print_error, print_warning, print_key_value, confirm, pause
)
from core.utils.paths import MODEL_REGISTRY

SETTINGS_FILE = MODEL_REGISTRY


# ─────────────────────────────────────────────────
# Settings helpers
# ─────────────────────────────────────────────────

def load_settings():
    """Load model registry / provider settings from disk."""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print_error(f"Failed to load settings: {e}")
        return {}


def save_settings(data):
    """Persist settings to disk."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print_error(f"Failed to save settings: {e}")
        return False


# ─────────────────────────────────────────────────
# Sub-menus
# ─────────────────────────────────────────────────

def show_providers_menu():
    """Toggle provider active/disabled state."""
    while True:
        clear_screen()
        print_header("Provider Settings", "Manage Active API Providers")

        settings  = load_settings()
        providers = settings.get("providers", {})

        if not providers:
            print_error("No providers found in model_registry.json")
            pause()
            return

        options   = []
        prov_list = []

        for key, data in providers.items():
            if key in ['default', 'fallback_order']:
                continue
            status = "[green]Enabled[/green]" if data.get('active') else "[dim]Disabled[/dim]"
            options.append(f"{key} — {status}")
            prov_list.append(key)

        print_menu("Available Providers", options)
        choice = get_user_choice(len(options), "Select provider to toggle, or 0 to back")

        if choice == 0:
            break

        selected_prov = prov_list[choice - 1]
        prov_data     = providers[selected_prov]

        current_state    = prov_data.get('active', False)
        prov_data['active'] = not current_state

        if save_settings(settings):
            action = "Enabled" if prov_data['active'] else "Disabled"
            print_success(f"{action} {selected_prov}")
            if not confirm("Continue?", default=True):
                break


def show_identity_menu():
    """View Misaka's base identity and dynamic memory."""
    while True:
        clear_screen()
        print_header("Identity Profile", "Misaka's Persistent Identity Files")

        options = [
            "View Base Info    — Personality, name, traits",
            "View Dynamic Memory — User info & observations",
        ]
        print_menu("Identity", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break

        try:
            from core.memory.identity_manager import IdentityManager
        except ImportError:
            print_error("IdentityManager not available.")
            pause()
            return

        if choice == 1:
            clear_screen()
            print_header("Base Info", "Personality & Identity (base_info.json)")
            data = IdentityManager.get_base_info()
            if not data:
                print_warning("base_info.json is empty or does not exist yet.")
            else:
                console.print_json(json.dumps(data))
            pause()

        elif choice == 2:
            clear_screen()
            print_header("Dynamic Memory", "User Info & Observations (memory.json)")
            data = IdentityManager.get_dynamic_memory()
            if not data:
                print_warning("memory.json is empty or does not exist yet.")
            else:
                last_updated = data.get("last_updated", "Unknown")
                user_info    = data.get("user_info", {})
                observations = data.get("recent_observations", [])

                print_key_value("Last Updated", last_updated)

                console.print("\n[bold cyan]User Info:[/bold cyan]")
                if user_info:
                    for k, v in user_info.items():
                        print_key_value(f"  {k}", v)
                else:
                    console.print("  [dim]No user info stored yet.[/dim]")

                console.print(f"\n[bold cyan]Recent Observations ({len(observations)}):[/bold cyan]")
                if observations:
                    for i, obs in enumerate(observations[-15:], 1):
                        console.print(f"  [dim]{i}.[/dim] {obs}")
                else:
                    console.print("  [dim]No observations stored yet.[/dim]")
            pause()


def show_social_registry_menu():
    """View the Social Registry (Discord user mappings)."""
    clear_screen()
    print_header("Social Registry", "Platform-to-Profile Mappings")

    try:
        from core.memory.social_registry import get_social_registry
        registry = get_social_registry()
    except ImportError:
        print_error("SocialRegistry not available.")
        pause()
        return

    profiles = registry.registry

    if not profiles:
        print_warning("Social Registry is empty. No users mapped yet.")
        console.print("[dim]Users are automatically added when they interact via Discord.[/dim]")
        pause()
        return

    from rich.table import Table
    table = Table(title=f"Social Registry ({len(profiles)} profiles)", show_lines=False)
    table.add_column("Key",          style="dim",         width=26)
    table.add_column("Display Name", style="bold yellow", width=18)
    table.add_column("Platform",     style="cyan",        width=10)
    table.add_column("Last Seen",    style="dim",         width=22)

    for key, profile in sorted(profiles.items()):
        table.add_row(
            key,
            profile.get("display_name", "?"),
            profile.get("platform", "?"),
            str(profile.get("last_seen", "?"))[:19],
        )

    console.print(table)
    pause()


def show_raw_settings():
    """Show raw model registry JSON (read-only)."""
    clear_screen()
    print_header("Raw Settings", "model_registry.json (Read-Only)")
    data = load_settings()
    if data:
        console.print_json(json.dumps(data))
    else:
        print_warning("Settings file is empty or not found.")
    pause()


# ─────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────

def settings_module():
    """Main entry point for Settings CLI module."""
    while True:
        clear_screen()
        print_header("Settings & Configuration", "System Preferences")

        options = [
            "Manage Providers    — Toggle active AI providers",
            "Identity Profile    — View base info & dynamic memory",
            "Social Registry     — View Discord user mappings",
            "View Raw Settings   — model_registry.json (read-only)",
        ]

        print_menu("Settings Menu", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break
        elif choice == 1:
            show_providers_menu()
        elif choice == 2:
            show_identity_menu()
        elif choice == 3:
            show_social_registry_menu()
        elif choice == 4:
            show_raw_settings()
