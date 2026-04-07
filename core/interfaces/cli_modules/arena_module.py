"""
Misaka Cipher - Arena Module
CLI interface for testing LLM models against each other
"""

from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    get_text_input, print_success, print_error, confirm, show_progress,
    print_key_value, pause
)
from core.interfaces.cli_modules.settings_module import load_settings
from rich.panel import Panel
from rich.columns import Columns
from rich.table import Table
from pathlib import Path
import asyncio
import time
import uuid
from core.utils.paths import APP_ARENA
from core.ai.call_contexts import CallSource

_LEADERBOARD_FILE = APP_ARENA / "leaderboard.json"

def _get_active_models():
    """Extract list of available model strings from enabled providers."""
    settings = load_settings()
    providers = settings.get("providers", {})
    available = []
    
    for prov_name, data in providers.items():
        if prov_name in ['default', 'fallback_order']:
            continue
        if data.get('active'):
            # Some providers have 'models' list, some are simple placeholders.
            # In a real setup, we query the NexusCore. For CLI simplicity, we mock generic options.
            available.append(f"{prov_name} (default)")
            for m in data.get('models', []):
                available.append(f"{prov_name}/{m}")
                
    return available if available else ["google_ai (fallback)"]

def run_battle(nexus, prompt: str, model1: str, model2: str):
    """Run an arena battle between two models."""
    trace_id = f"CLI_ARENA_{uuid.uuid4().hex[:8]}"
    
    # Strip provider prefix if structured like provider/model
    m1_clean = model1.split('/')[-1] if '/' in model1 else "auto"
    m2_clean = model2.split('/')[-1] if '/' in model2 else "auto"
    
    m1_prov = model1.split('/')[0] if '/' in model1 else model1.split(' ')[0]
    m2_prov = model2.split('/')[0] if '/' in model2 else model2.split(' ')[0]

    console.print(f"\n[cyan]Battle ID:[/cyan] {trace_id}")
    console.print(f"[cyan]Prompt:[/cyan] {prompt}\n")
    
    # Run async calls concurrently
    async def _call_both():
        t1, t2 = time.time(), time.time()
        res1, res2 = None, None
        
        # We need to dispatch via provider manager
        # Since call_with_failover is sync in some branches and async in others, 
        # we'll use run_in_executor/to_thread to be safe.
        
        async def fetch_1():
            nonlocal t1, res1
            t1 = time.time()
            res1 = await asyncio.to_thread(
                nexus.provider_manager.call_with_failover,
                prompt=prompt, trace_id=trace_id+"_1", model=m1_clean, source=CallSource.ARENA
            )
            return time.time() - t1
            
        async def fetch_2():
            nonlocal t2, res2
            t2 = time.time()
            res2 = await asyncio.to_thread(
                nexus.provider_manager.call_with_failover,
                prompt=prompt, trace_id=trace_id+"_2", model=m2_clean, source=CallSource.ARENA
            )
            return time.time() - t2
            
        d1, d2 = await asyncio.gather(fetch_1(), fetch_2())
        return (res1, d1), (res2, d2)
        
    with show_progress("Generating responses...") as progress:
        progress.add_task("battling", total=None)
        # Execute the battle
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        result1, result2 = loop.run_until_complete(_call_both())
        
    # Render Output
    clear_screen()
    print_header("Arena Results")
    
    res1_obj, dur1 = result1
    res2_obj, dur2 = result2
    
    c1 = res1_obj.content if res1_obj and res1_obj.success else f"Error: {res1_obj.error if res1_obj else 'Unknown Timeout'}"
    c2 = res2_obj.content if res2_obj and res2_obj.success else f"Error: {res2_obj.error if res2_obj else 'Unknown Timeout'}"
    
    p1 = Panel(c1, title=f"[bold]{model1}[/bold] ({dur1:.2f}s)", border_style="blue")
    p2 = Panel(c2, title=f"[bold]{model2}[/bold] ({dur2:.2f}s)", border_style="red")
    
    console.print(Columns([p1, p2]))
    
    # Winner Selection
    print_menu("Declare Winner", [model1, model2, "Tie/Both Failed"])
    win_choice = get_user_choice(3)
    
    if win_choice > 0:
        winner = model1 if win_choice == 1 else (model2 if win_choice == 2 else "tie")
        
        # Update Leaderboard JSON backing file
        import json
        lb_file = _LEADERBOARD_FILE
        lb_file.parent.mkdir(parents=True, exist_ok=True)
        
        lb_data = {"models": {}}
        if lb_file.exists():
            with open(lb_file, 'r') as f:
                lb_data = json.load(f)
                
        def _ensure(m):
            if m not in lb_data["models"]:
                lb_data["models"][m] = {"wins": 0, "losses": 0, "ties": 0, "win_rate": 0}
                
        _ensure(model1)
        _ensure(model2)
        
        if winner == "tie":
            lb_data["models"][model1]["ties"] += 1
            lb_data["models"][model2]["ties"] += 1
        elif winner == model1:
            lb_data["models"][model1]["wins"] += 1
            lb_data["models"][model2]["losses"] += 1
        elif winner == model2:
            lb_data["models"][model2]["wins"] += 1
            lb_data["models"][model1]["losses"] += 1
            
        # Calc rates
        for m in [model1, model2]:
            st = lb_data["models"][m]
            total = st["wins"] + st["losses"] + st["ties"]
            if total > 0:
                st["win_rate"] = round((st["wins"] / total) * 100, 1)
                
        with open(lb_file, 'w') as f:
            json.dump(lb_data, f, indent=2)
            
        print_success(f"Results recorded! Winner: {winner}")
    
    pause()


def arena_module(nexus):
    """Interactive Arena Module entry point."""
    while True:
        clear_screen()
        print_header("LLM Arena", "Model vs Model Battles")
        
        options = [
            "Start Standard Battle",
            "View Local Leaderboard"
        ]
        
        print_menu("Arena Menu", options)
        choice = get_user_choice(len(options))
        
        if choice == 0:
            break
        elif choice == 1:
            # Setup Battle
            models = _get_active_models()
            if len(models) < 2:
                print_error("Need at least 2 active models/providers configured in settings to duel.")
                pause()
                continue
                
            clear_screen()
            print_header("Configure Battle")
            
            print_menu("Select Model 1 (Blue Corner)", models, include_exit=False)
            c1 = get_user_choice(len(models), "Choice")
            if c1 == 0: continue
            
            print_menu("Select Model 2 (Red Corner)", models, include_exit=False)
            c2 = get_user_choice(len(models), "Choice")
            if c2 == 0: continue
            
            m1 = models[c1-1]
            m2 = models[c2-1]
            
            console.print(f"\n[cyan]Matchup:[/cyan] [bold blue]{m1}[/bold blue] vs [bold red]{m2}[/bold red]")
            prompt = get_text_input("Enter battle prompt", multiline=True)
            if not prompt.strip():
                continue
                
            run_battle(nexus, prompt, m1, m2)
            
        elif choice == 2:
            clear_screen()
            print_header("Arena Leaderboard")
            import json
            lb_file = _LEADERBOARD_FILE
            if not lb_file.exists():
                print_error("No battles recorded yet.")
            else:
                with open(lb_file, 'r') as f:
                    lb_data = json.load(f)
                    
                table = Table(title="Win/Loss Record")
                table.add_column("Model")
                table.add_column("Win Rate", justify="right")
                table.add_column("W/L/T")
                
                # Sort by win rate desc
                sorted_models = sorted(
                    lb_data["models"].items(), 
                    key=lambda x: (x[1]["win_rate"], x[1]["wins"]), 
                    reverse=True
                )
                
                for m, stats in sorted_models:
                    wrate = f"{stats['win_rate']}%"
                    wlt = f"{stats['wins']}/{stats['losses']}/{stats['ties']}"
                    table.add_row(m, wrate, wlt)
                    
                console.print(table)
            pause()
