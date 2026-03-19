"""
Misaka Cipher - Memory Module
Memory Tier query interface
"""

from pathlib import Path
from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    get_text_input, print_table, print_key_value, pause, print_info,
    print_warning, confirm, print_error
)
from core.memory import get_episodic_memory, get_knowledge_graph
from core.utils.paths import WS_PROJECTS, HISTORY_ADVANCED
from rich.panel import Panel
from rich.tree import Tree
from rich.table import Table
import json

_WORKSPACES_DIR = WS_PROJECTS
_AICONV_DIR     = HISTORY_ADVANCED / "threads"


def memory_module():
    """Interactive Memory Tier query interface."""

    memory_store = get_episodic_memory()
    kg = get_knowledge_graph()

    while True:
        clear_screen()
        print_header("The Memory Tier", "Knowledge & Context Management")

        options = [
            "Semantic Search          — Episodic Memory",
            "Browse Knowledge Graph   — Domains, Tools, Agents",
            "Trace_ID Lookup          — Audit Trail Explorer",
            "Memory Statistics        — Overview of Stored Knowledge",
            "Search Workspaces        — Workspace Threads",
            "Advanced AI Conversations — Simulation Threads",
            "Identity Profile         — Base Info & Dynamic Memory",
        ]

        print_menu("Memory Operations", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break

        if choice == 1:
            _semantic_search(memory_store)
        elif choice == 2:
            _browse_knowledge_graph(kg)
        elif choice == 3:
            _trace_lookup(memory_store, kg)
        elif choice == 4:
            _memory_stats(memory_store, kg)
        elif choice == 5:
            _search_workspaces()
        elif choice == 6:
            _search_aiconv()
        elif choice == 7:
            _view_identity_profile()


def chat_history_module():
    """Standalone Chat History Browser — entry point from main menu."""
    _browse_chat_history()


# ─────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────

def _semantic_search(memory_store):
    """Semantic search interface."""
    clear_screen()
    print_header("Semantic Search", "Query Episodic Memory")

    query = get_text_input("\nSearch Query")

    if not query.strip():
        return

    # Optional domain filter
    console.print()
    use_domain = confirm("Filter by domain?", default=False)
    domain = None

    if use_domain:
        domain = get_text_input("Domain (Finance, Data, Security, etc.)")

    # Search
    results = memory_store.search(query, k=10, domain=domain if domain else None)

    console.print("\n" + "═" * 50 + "\n")

    if results:
        print_info(f"Found {len(results)} results:")
        console.print()

        for i, memory in enumerate(results, 1):
            console.print(f"[bold yellow]{i}. {memory.summary}[/bold yellow]")
            print_key_value("  Event Type", memory.event_type)
            print_key_value("  Domain", memory.domain)
            print_key_value("  Timestamp", memory.timestamp)
            print_key_value("  Trace ID", memory.trace_id)
            console.print()
    else:
        print_warning("No results found")

    pause()


def _browse_knowledge_graph(kg):
    """Knowledge graph browser."""

    while True:
        clear_screen()
        print_header("Knowledge Graph", "Browse Domains, Tools, and Agents")

        options = [
            "List All Domains",
            "List Tools by Domain",
            "List Agents by Domain",
            "View Graph Statistics"
        ]

        print_menu("Knowledge Graph", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break

        if choice == 1:
            # List domains
            domains = kg.get_domains()
            console.print("\n[bold cyan]Domains:[/bold cyan]\n")
            for domain in domains:
                console.print(f"  • {domain}")
            pause()

        elif choice == 2:
            # List tools by domain
            domain = get_text_input("\nDomain name")
            if domain:
                tools = kg.get_tools_by_domain(domain)
                console.print(f"\n[bold cyan]{domain} Tools:[/bold cyan]\n")
                if tools:
                    for tool in tools:
                        console.print(f"  • {tool}")
                else:
                    print_warning(f"No tools found in {domain}")
                pause()

        elif choice == 3:
            # List agents by domain
            domain = get_text_input("\nDomain name")
            if domain:
                agents = kg.get_agents_by_domain(domain)
                console.print(f"\n[bold cyan]{domain} Agents:[/bold cyan]\n")
                if agents:
                    for agent in agents:
                        console.print(f"  • {agent}")
                else:
                    print_warning(f"No agents found in {domain}")
                pause()

        elif choice == 4:
            # Graph stats
            stats = kg.get_stats()
            console.print("\n[bold cyan]Knowledge Graph Statistics:[/bold cyan]\n")
            print_key_value("Total Nodes", stats['total_nodes'])
            print_key_value("Total Edges", stats['total_edges'])
            print_key_value("Domains", stats['domains'])

            console.print("\n[bold yellow]Node Types:[/bold yellow]")
            for node_type, count in stats['node_types'].items():
                console.print(f"  • {node_type}: {count}")

            pause()


def _trace_lookup(memory_store, kg):
    """Trace ID lookup interface."""
    clear_screen()
    print_header("Trace_ID Lookup", "Audit Trail Explorer")

    trace_id = get_text_input("\nTrace_ID")

    if not trace_id.strip():
        return

    # Get memories
    memories = memory_store.get_by_trace_id(trace_id)

    console.print("\n" + "═" * 50 + "\n")

    if memories:
        print_info(f"Found {len(memories)} memory/memories for {trace_id}:")
        console.print()

        for memory in memories:
            panel = Panel(
                f"[bold]Summary:[/bold] {memory.summary}\n"
                f"[bold]Event Type:[/bold] {memory.event_type}\n"
                f"[bold]Domain:[/bold] {memory.domain}\n"
                f"[bold]Timestamp:[/bold] {memory.timestamp}\n\n"
                f"[bold]Content:[/bold]\n{memory.content}",
                title=f"Memory: {memory.memory_id}",
                border_style="cyan"
            )
            console.print(panel)
            console.print()
    else:
        print_warning(f"No memories found for Trace_ID: {trace_id}")

    # Check knowledge graph
    node_info = kg.get_node_info(trace_id)
    if node_info:
        console.print("[bold cyan]Knowledge Graph Entry:[/bold cyan]\n")
        for key, value in node_info.items():
            print_key_value(key, value)

    pause()


def _memory_stats(memory_store, kg):
    """Display memory statistics."""
    clear_screen()
    print_header("Memory Statistics", "Overview of Stored Knowledge")

    memory_count = memory_store.get_count()
    stats = kg.get_stats()

    console.print()
    print_key_value("Episodic Memories", memory_count)
    print_key_value("Knowledge Graph Nodes", stats['total_nodes'])
    print_key_value("Knowledge Graph Edges", stats['total_edges'])
    print_key_value("Active Domains", stats['domains'])

    console.print("\n[bold yellow]Node Type Distribution:[/bold yellow]")
    for node_type, count in stats['node_types'].items():
        console.print(f"  • {node_type}: {count}")

    # Also show today's chat history message count
    try:
        from core.memory.history_manager import HistoryManager
        today_count = HistoryManager.get_total_message_count()
        console.print()
        print_key_value("Chat History (today)", f"{today_count} messages")
    except Exception:
        pass

    pause()


def _search_workspaces():
    """Browse workspace threads."""
    clear_screen()
    print_header("Workspace Threads", "Browse Task Threads")

    if not _WORKSPACES_DIR.exists():
        print_error(f"Workspaces directory not found: {_WORKSPACES_DIR}")
        pause()
        return

    threads = []
    t_paths = []
    for d in sorted(_WORKSPACES_DIR.iterdir()):
        if d.is_dir() and d.name.startswith("thread-"):
            meta_file = d / f"{d.name}.json"
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    name = meta.get("title", "Unnamed Thread")
                    threads.append(f"{name} ({d.name})")
                    t_paths.append(d)

    if not threads:
        print_error("No workspace threads found.")
        pause()
        return

    print_menu("Select Thread", threads)
    c = get_user_choice(len(threads))
    if c == 0:
        return
    selected_dir = t_paths[c - 1]

    meta_file = selected_dir / f"{selected_dir.name}.json"
    meta = {}
    if meta_file.exists():
        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

    while True:
        clear_screen()
        print_header(f"Thread: {meta.get('title', 'Unknown')}", "Workspace Task Browser")
        print_key_value("ID",      meta.get('id', selected_dir.name))
        print_key_value("Mode",    meta.get('mode', 'chat'))
        print_key_value("Created", meta.get('created_at', 'Unknown'))

        tasks_dir = selected_dir / "tasks"
        tasks = []
        if tasks_dir.exists():
            for f in tasks_dir.glob("*.json"):
                with open(f, 'r', encoding='utf-8') as fh:
                    tasks.append(json.load(fh))

        console.print(f"\n[bold cyan]Found {len(tasks)} task entries.[/bold cyan]")
        search_q = get_text_input("\nFilter (empty = all, 'exit' to go back)")
        if search_q.lower() == 'exit':
            break

        table = Table(title="Task Entries", show_lines=False)
        table.add_column("Task ID",   style="bold yellow", width=10)
        table.add_column("Type",      style="cyan",        width=14)
        table.add_column("Preview",   overflow="fold")

        for t in sorted(tasks, key=lambda x: x.get('created_at', '')):
            content = json.dumps(t)
            if search_q.lower() in content.lower() or not search_q.strip():
                task_type = t.get('task_type', 'unknown')
                preview = str(t.get('input_data', {}))[:100] + "…"
                table.add_row(t.get('id', '??')[:8], task_type, preview)

        console.print(table)
        pause()


def _search_aiconv():
    """Browse Advanced AI Conversation simulation threads."""
    clear_screen()
    print_header("Advanced AI Conversations", "Simulation Thread Browser")

    if not _AICONV_DIR.exists():
        print_error(f"Advanced AI Conversation directory not found: {_AICONV_DIR}")
        pause()
        return

    threads = []
    t_paths = []
    for d in sorted(_AICONV_DIR.iterdir()):
        if d.is_dir():
            meta_file = d / "meta.json"
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    name  = meta.get("name", "Unnamed Thread")
                    topic = meta.get("topic", "")
                    threads.append(f"{name} | {topic}")
                    t_paths.append(d)

    if not threads:
        print_error("No Advanced AI Conversation threads found.")
        pause()
        return

    print_menu("Select Simulation Thread", threads)
    c = get_user_choice(len(threads))
    if c == 0:
        return
    selected_dir = t_paths[c - 1]

    with open(selected_dir / "meta.json", 'r', encoding='utf-8') as f:
        meta = json.load(f)

    while True:
        clear_screen()
        print_header(f"Simulation: {meta.get('name', 'Unknown')}", "Message Browser")
        print_key_value("Topic",           meta.get('topic', 'N/A'))
        print_key_value("Created",         meta.get('created_at', 'Unknown'))
        print_key_value("Participant IDs", ", ".join(meta.get('active_person_ids', [])))

        msg_file = selected_dir / "messages.json"
        msgs = []
        if msg_file.exists():
            with open(msg_file, 'r', encoding='utf-8') as f:
                msgs = json.load(f)

        console.print(f"\n[bold cyan]Found {len(msgs)} messages.[/bold cyan]")
        search_q = get_text_input("\nFilter (empty = all, 'exit' to go back)")
        if search_q.lower() == 'exit':
            break

        table = Table(title="Simulation Messages", show_lines=False)
        table.add_column("Role", style="bold yellow", width=12)
        table.add_column("Name", style="cyan",        width=14)
        table.add_column("Content", overflow="fold")

        for m in msgs:
            content = m.get('content', '')
            match = (
                search_q.lower() in content.lower()
                or search_q.lower() in m.get('name', '').lower()
                or not search_q.strip()
            )
            if match:
                preview = content[:120] + ("…" if len(content) > 120 else "")
                table.add_row(m.get('role', '??'), m.get('name', '??'), preview)

        console.print(table)
        pause()


def _browse_chat_history():
    """Browse unified chat history (Dashboard + Discord)."""
    while True:
        clear_screen()
        print_header("Chat History", "Unified Dashboard + Discord History")

        try:
            from core.memory.history_manager import HistoryManager
        except ImportError:
            print_error("HistoryManager not available.")
            pause()
            return

        options = [
            "View Today's History",
            "View Yesterday's History",
            "Browse by Day Offset",
            "Search Across Recent Days",
        ]
        print_menu("Chat History", options)
        choice = get_user_choice(len(options))

        if choice == 0:
            break
        elif choice == 1:
            _show_history_day(HistoryManager, offset=0)
        elif choice == 2:
            _show_history_day(HistoryManager, offset=1)
        elif choice == 3:
            offset_str = get_text_input("Days ago (0 = today, 1 = yesterday, ...)", default="0")
            try:
                _show_history_day(HistoryManager, offset=int(offset_str))
            except ValueError:
                print_error("Invalid number.")
                pause()
        elif choice == 4:
            _search_history(HistoryManager)


def _show_history_day(HistoryManager, offset: int = 0):
    """Show chat history for a specific day."""
    import datetime
    target = datetime.datetime.now() - datetime.timedelta(days=offset)
    date_str = target.strftime("%Y-%m-%d")

    clear_screen()
    label = "Today" if offset == 0 else ("Yesterday" if offset == 1 else f"{offset} days ago")
    print_header(f"Chat History — {label}", date_str)

    days = HistoryManager.get_history(offset_days=offset, limit_days=1)
    if not days or not days[0]["messages"]:
        print_warning(f"No history found for {date_str}.")
        pause()
        return

    messages = days[0]["messages"]

    # Platform breakdown
    platforms = {}
    for m in messages:
        p = m.get("platform", "unknown")
        platforms[p] = platforms.get(p, 0) + 1

    print_key_value("Total messages", len(messages))
    for plat, cnt in platforms.items():
        console.print(f"  • [cyan]{plat}[/cyan]: {cnt} messages")
    console.print()

    # Optional platform filter
    filter_platform = None
    if len(platforms) > 1:
        plat_options = list(platforms.keys())
        if confirm("Filter by platform?", default=False):
            print_menu("Platform", plat_options, include_exit=False)
            pc = get_user_choice(len(plat_options), "Choice")
            if pc > 0:
                filter_platform = plat_options[pc - 1]

    table = Table(title=f"Messages — {date_str}", show_lines=True)
    table.add_column("Time",     style="dim",         width=8)
    table.add_column("Platform", style="cyan",        width=10)
    table.add_column("Role",     style="bold yellow", width=10)
    table.add_column("Content",  overflow="fold")

    shown = 0
    for m in messages:
        plat = m.get("platform", "unknown")
        if filter_platform and plat != filter_platform:
            continue
        ts = m.get("timestamp", "")
        time_part = ts.split(" ")[-1] if " " in ts else ts
        role = m.get("role", "??")
        content = m.get("content", "")
        preview = content[:200] + ("…" if len(content) > 200 else "")
        role_style = "green" if role == "assistant" else "white"
        table.add_row(time_part, plat, f"[{role_style}]{role}[/{role_style}]", preview)
        shown += 1

    console.print(table)
    console.print(f"\n[dim]Showing {shown} messages[/dim]")
    pause()


def _search_history(HistoryManager):
    """Search across recent chat history."""
    clear_screen()
    print_header("Search Chat History", "Search Across Last 7 Days")

    query = get_text_input("Search term")
    if not query.strip():
        return

    days = HistoryManager.get_history(offset_days=0, limit_days=7)
    results = []
    for day in days:
        for m in day["messages"]:
            if query.lower() in m.get("content", "").lower():
                results.append({**m, "_date": day["date"]})

    console.print(f"\n[bold cyan]Found {len(results)} matches for '{query}':[/bold cyan]\n")

    if not results:
        print_warning("No matches found.")
        pause()
        return

    table = Table(title=f"Search: {query}", show_lines=True)
    table.add_column("Date",     style="dim",         width=12)
    table.add_column("Platform", style="cyan",        width=10)
    table.add_column("Role",     style="bold yellow", width=10)
    table.add_column("Content",  overflow="fold")

    for m in results[-50:]:  # cap at 50 for display
        content = m.get("content", "")
        # Highlight the query term
        highlighted = content.replace(query, f"[bold yellow]{query}[/bold yellow]")
        preview = highlighted[:250] + ("…" if len(content) > 250 else "")
        role = m.get("role", "??")
        table.add_row(m.get("_date", "?"), m.get("platform", "?"), role, preview)

    console.print(table)
    if len(results) > 50:
        print_warning(f"Showing last 50 of {len(results)} matches.")
    pause()


def _view_identity_profile():
    """View Misaka's identity and dynamic memory files."""
    while True:
        clear_screen()
        print_header("Identity Profile", "Base Info & Dynamic Memory")

        options = [
            "View Base Info (Personality & Identity)",
            "View Dynamic Memory (User Info & Observations)",
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
            print_header("Base Info", "Personality & Identity")
            data = IdentityManager.get_base_info()
            if not data:
                print_warning("base_info.json is empty or not found.")
            else:
                import json as _json
                console.print_json(_json.dumps(data))
            pause()

        elif choice == 2:
            clear_screen()
            print_header("Dynamic Memory", "User Info & Recent Observations")
            data = IdentityManager.get_dynamic_memory()
            if not data:
                print_warning("memory.json is empty or not found.")
            else:
                user_info = data.get("user_info", {})
                observations = data.get("recent_observations", [])
                last_updated = data.get("last_updated", "Unknown")

                print_key_value("Last Updated", last_updated)

                if user_info:
                    console.print("\n[bold cyan]User Info:[/bold cyan]")
                    for k, v in user_info.items():
                        print_key_value(f"  {k}", v)
                else:
                    print_warning("No user info stored yet.")

                if observations:
                    console.print(f"\n[bold cyan]Recent Observations ({len(observations)}):[/bold cyan]")
                    for i, obs in enumerate(observations[-10:], 1):
                        console.print(f"  [dim]{i}.[/dim] {obs}")
                else:
                    print_warning("No observations stored yet.")
            pause()
