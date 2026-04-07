"""
Misaka Cipher - Research Module
CLI interface for Advanced AI Conversations
"""

from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    get_text_input, print_success, print_error, confirm, show_progress,
    pause
)
from core.interfaces.cli_modules.settings_module import load_settings
from rich.panel import Panel
from rich.table import Table
import asyncio
import time
import uuid
from datetime import datetime
from core.utils import utcnow_iso
import json
from pathlib import Path
from core.utils.paths import HISTORY_ADVANCED
from core.ai.call_contexts import CallSource

PEOPLE_DIR = HISTORY_ADVANCED / "people"
THREADS_DIR = HISTORY_ADVANCED / "threads"

def init_dirs():
    PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    THREADS_DIR.mkdir(parents=True, exist_ok=True)

def _get_active_models():
    settings = load_settings()
    providers = settings.get("providers", {})
    available = []
    
    for prov_name, data in providers.items():
        if prov_name in ['default', 'fallback_order']:
            continue
        if data.get('active'):
            available.append(f"{prov_name} (default)")
            for m in data.get('models', []):
                available.append(f"{prov_name}/{m}")
                
    return available if available else ["google_ai (fallback)"]

def create_persona():
    clear_screen()
    print_header("Create New Research Persona")
    
    name = get_text_input("Name")
    if not name.strip(): return
    gender = get_text_input("Gender/Pronouns", default="unknown")
    background = get_text_input("Background / System Prompt", multiline=True)
    
    console.print("\n[yellow]Now define a few core traits for tracking (e.g., 'trust', 'anxiety', 'curiosity').[/yellow]")
    traits = {}
    while True:
        t_name = get_text_input("Trait Name (leave empty to finish)")
        if not t_name.strip(): break
        t_val = get_text_input(f"Initial value for {t_name} (1-10)", default="5")
        try:
            traits[t_name] = int(t_val)
        except ValueError:
            print_error("Must be an integer.")
            
    models = _get_active_models()
    print_menu("Select Dedicated Model", models)
    m_choice = get_user_choice(len(models))
    model = models[m_choice-1] if m_choice > 0 else "auto"
    
    pid = uuid.uuid4().hex[:8]
    data = {
        "id": pid,
        "name": name,
        "gender": gender,
        "background": background,
        "traits": traits,
        "original_traits": traits.copy(),
        "memory": "",
        "original_memory": "",
        "message_count": 0,
        "model": model,
        "created_at": utcnow_iso()
    }
    
    with open(PEOPLE_DIR / f"{pid}.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
        
    print_success(f"Persona '{name}' created successfully with ID {pid}.")
    pause()

def view_personas():
    clear_screen()
    print_header("Active Personas")
    
    people_files = list(PEOPLE_DIR.glob("*.json"))
    if not people_files:
        print_error("No personas found.")
        pause()
        return
        
    table = Table(title="Database")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Model")
    table.add_column("Messages Sent")
    
    for pf in people_files:
        with open(pf, 'r') as f:
            d = json.load(f)
            table.add_row(d.get('id', '??'), d.get('name', '??'), d.get('model', 'auto'), str(d.get('message_count', 0)))
            
    console.print(table)
    pause()

def run_simulation(nexus, thread_id: str):
    t_dir = THREADS_DIR / thread_id
    with open(t_dir / "meta.json", 'r') as f:
        meta = json.load(f)
    
    with open(t_dir / "messages.json", 'r') as f:
        messages = json.load(f)
        
    active_ids = meta.get("active_person_ids", [])
    if not active_ids:
        print_error("No active personas assigned to this thread.")
        pause()
        return
        
    # Start Loop
    while True:
        clear_screen()
        print_header(f"Simulation: {meta.get('name', thread_id)}")
        
        # Display history
        if not messages:
            console.print("[dim]Thread is empty. Generate a turn to begin.[/dim]\n")
        else:
            for m in messages[-10:]: # Show last 10
                if m.get('role') == 'system':
                    console.print(f"[bold red]SYSTEM:[/bold red] {m.get('content')}")
                else:
                    tldr = m.get('tldr', '')
                    tldr_str = f" [dim magenta]({tldr})[/dim magenta]" if tldr else ""
                    console.print(f"[bold cyan]{m.get('name')}:[/bold cyan] {m.get('content')}{tldr_str}")
            console.print()
                
        print_menu("Actions", ["Next Turn (Round Robin)", "Inject System Event Event", "Exit Simulation"])
        c = get_user_choice(3)
        
        if c == 3 or c == 0:
            break
        elif c == 2:
            sys_event = get_text_input("Enter system event")
            if sys_event.strip():
                messages.append({
                    "id": uuid.uuid4().hex[:8],
                    "role": "system",
                    "content": sys_event,
                    "timestamp": utcnow_iso()
                })
                with open(t_dir / "messages.json", 'w') as f:
                    json.dump(messages, f, indent=4)
            continue
        elif c == 1:
            # Pick next person round robin
            last_speaker = None
            for i in range(len(messages)-1, -1, -1):
                if messages[i].get('role') == 'person':
                    last_speaker = messages[i].get('person_id')
                    break
                    
            next_idx = 0
            if last_speaker in active_ids:
                idx = active_ids.index(last_speaker)
                next_idx = (idx + 1) % len(active_ids)
                
            speaker_id = active_ids[next_idx]
            p_file = PEOPLE_DIR / f"{speaker_id}.json"
            if not p_file.exists(): 
                print_error(f"Persona {speaker_id} file missing!")
                pause()
                continue
                
            with open(p_file, 'r') as f:
                speaker = json.load(f)
                
            # Build Prompt
            system_prompt = f"""You are {speaker['name']}. ({speaker['gender']}).
            
BACKGROUND:
{speaker['background']}

CURRENT INTERNAL MEMORY STATE:
{speaker['memory']}

CURRENT EMOTIONAL/PSYCHOLOGICAL TRAITS (1-10):
{json.dumps(speaker['traits'], indent=2)}

You are in a simulation. The user has provided context. You must look at the recent conversation history and decide what you say next.
CRITICAL: You MUST reply in the exact JSON format below. Do not wrap in markdown or backticks.

{{
    "spoken_response": "Your actual dialog and actions that everyone else sees. Be natural, stay in character.",
    "internal_monologue": "Your private thoughts on the situation.",
    "updated_traits": {{ "TraitName": 5, "OtherTrait": 7 }},
    "memory_updates": "A condensed, updated version of your memory incorporating new information learned in this interaction.",
    "trait_changes_tldr": "A 5-word summary of how your feelings/traits changed this turn, if at all."
}}
"""

            context_str = ""
            for m in messages[-20:]:
                if m.get('role') == 'system': context_str += f"System Event: {m['content']}\n"
                else: context_str += f"{m.get('name', 'Unknown')}: {m['content']}\n"
                
            prompt = f"Recent conversation:\n{context_str}\n\nWhat do you say next {speaker['name']}? Reply in JSON."
            
            trace_id = f"RES_{uuid.uuid4().hex[:8]}"
            model_clean = speaker.get('model', 'auto').split('/')[-1] if '/' in speaker.get('model', 'auto') else "auto"
            
            with show_progress(f"{speaker['name']} is thinking...") as progress:
                progress.add_task("generating", total=None)
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                async def fetch():
                    return await asyncio.to_thread(
                        nexus.provider_manager.call_with_failover,
                        prompt=prompt, system_prompt=system_prompt, trace_id=trace_id, 
                        model=model_clean, source=CallSource.RESEARCH, json_mode=True
                    )
                
                resp = loop.run_until_complete(fetch())
                
            if not resp.success:
                print_error(f"Generation failed: {resp.error}")
                pause()
                continue
                
            content = resp.content.strip()
            if content.startswith('```json'): content = content[7:]
            if content.startswith('```'): content = content[3:]
            if content.endswith('```'): content = content[:-3]
            content = content.strip()
            
            try:
                parsed = json.loads(content)
                speaker['traits'] = parsed.get("updated_traits", speaker['traits'])
                speaker['memory'] = parsed.get("memory_updates", speaker['memory'])
                speaker['message_count'] = speaker.get('message_count', 0) + 1
                
                # Save Person
                with open(p_file, 'w') as f:
                    json.dump(speaker, f, indent=4)
                    
                # Append Message
                msg_id = uuid.uuid4().hex[:8]
                new_msg = {
                    "id": msg_id, "role": "person", "person_id": speaker_id,
                    "name": speaker['name'], "content": parsed.get("spoken_response", ""),
                    "tldr": parsed.get("trait_changes_tldr", ""),
                    "timestamp": utcnow_iso()
                }
                messages.append(new_msg)
                
                with open(t_dir / "messages.json", 'w') as f:
                    json.dump(messages, f, indent=4)
                    
            except Exception as e:
                print_error(f"Failed to parse or apply generated turn: {e}")
                print_error("Raw output was: " + content[:200] + "...")
                pause()


def create_thread(nexus):
    clear_screen()
    print_header("Create Simulation Thread")
    
    name = get_text_input("Thread Name")
    if not name.strip(): return
    topic = get_text_input("Global Context / Topic Topic")
    
    people_files = list(PEOPLE_DIR.glob("*.json"))
    if not people_files:
        print_error("You must create personas first before launching a simulation thread.")
        pause()
        return
        
    avail_people = []
    pid_map = []
    for pf in people_files:
        with open(pf, 'r') as f:
            d = json.load(f)
            avail_people.append(f"{d.get('name')} ({d.get('gender')})")
            pid_map.append(d.get('id'))
            
    active_ids = []
    while True:
        console.print(f"\nCurrently added: {len(active_ids)}")
        print_menu("Select Personas to Add", avail_people)
        c = get_user_choice(len(avail_people), "Choice (0 to finish adding)")
        if c == 0: break
        
        pid = pid_map[c-1]
        if pid not in active_ids:
            active_ids.append(pid)
            print_success("Added.")
        else:
            print_error("Already in simulation.")
            
    if not active_ids:
        print_error("Need at least 1 persona!")
        pause()
        return
        
    thread_id = uuid.uuid4().hex[:12]
    t_dir = THREADS_DIR / thread_id
    t_dir.mkdir(parents=True, exist_ok=True)
    
    meta = {
        "id": thread_id, "name": name, "topic": topic, "created_at": utcnow_iso(),
        "updated_at": utcnow_iso(), "active_person_ids": active_ids
    }
    with open(t_dir / "meta.json", 'w') as f: json.dump(meta, f, indent=4)
    with open(t_dir / "messages.json", 'w') as f: json.dump([], f)
    with open(t_dir / "snapshots.json", 'w') as f: json.dump([], f)
    
    run_simulation(nexus, thread_id)
    
def load_thread(nexus):
    clear_screen()
    print_header("Load Simulation Thread")
    
    threads = []
    t_map = []
    for d in THREADS_DIR.iterdir():
        if d.is_dir() and (d / "meta.json").exists():
            with open(d / "meta.json", 'r') as f:
                meta = json.load(f)
                threads.append(f"{meta.get('name')} | Particpants: {len(meta.get('active_person_ids', []))}")
                t_map.append(meta.get('id'))
                
    if not threads:
        print_error("No threads found.")
        pause()
        return
        
    print_menu("Select Thread", threads)
    c = get_user_choice(len(threads))
    if c > 0:
        run_simulation(nexus, t_map[c-1])


def research_module(nexus):
    """Interactive Research Module entry point."""
    init_dirs()
    while True:
        clear_screen()
        print_header("Advanced AI Conversations", "Simulation Research Lab")
        
        options = [
            "Start New Simulation Thread",
            "Load Simulation Thread",
            "Create New Persona",
            "View Active Personas Database"
        ]
        
        print_menu("Lab Menu", options)
        choice = get_user_choice(len(options))
        
        if choice == 0:
            break
        elif choice == 1:
            create_thread(nexus)
        elif choice == 2:
            load_thread(nexus)
        elif choice == 3:
            create_persona()
        elif choice == 4:
            view_personas()
