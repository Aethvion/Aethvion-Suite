"""
Misaka Cipher - Factory Module
Agent spawning interface
"""

from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, print_menu, get_user_choice,
    get_text_input, format_trace_id, print_success, print_error,
    print_key_value, pause, show_progress, confirm
)
from core.factory import AgentFactory, AgentSpec
from core.utils.validators import ALLOWED_DOMAINS, ALLOWED_ACTIONS
from rich.panel import Panel


def factory_module(factory: AgentFactory):
    """
    Interactive agent spawning interface.
    
    Args:
        factory: AgentFactory instance
    """
    while True:
        clear_screen()
        print_header("The Factory", "Agent Spawning & Execution")
        
        console.print("\n[bold cyan]Agent Specification Builder[/bold cyan]\n")
        
        # Domain selection
        console.print("[bold yellow]Step 1: Select Domain[/bold yellow]")
        print_menu("Available Domains", ALLOWED_DOMAINS, include_exit=True)
        domain_choice = get_user_choice(len(ALLOWED_DOMAINS), "Select domain")
        
        if domain_choice == 0:
            break
        
        domain = ALLOWED_DOMAINS[domain_choice - 1]
        
        # Action selection
        console.print(f"\n[bold yellow]Step 2: Select Action[/bold yellow]")
        print_menu("Available Actions", ALLOWED_ACTIONS, include_exit=True)
        action_choice = get_user_choice(len(ALLOWED_ACTIONS), "Select action")
        
        if action_choice == 0:
            continue
        
        action = ALLOWED_ACTIONS[action_choice - 1]
        
        # Object input
        console.print(f"\n[bold yellow]Step 3: Enter Object[/bold yellow]")
        console.print("[dim]What will the agent operate on? (e.g., 'Portfolio', 'StockPrice')[/dim]")
        obj = get_text_input("Object")
        
        if not obj.strip():
            print_error("Object cannot be empty")
            pause()
            continue
        
        # Construct agent name
        agent_name = f"{domain}_{action}_{obj}"
        console.print(f"\n[bold green]Agent Name:[/bold green] {agent_name}")
        
        # Context/Prompt input
        console.print(f"\n[bold yellow]Step 4: Enter Agent Prompt[/bold yellow]")
        console.print("[dim]What task should the agent perform?[/dim]")
        prompt = get_text_input("Prompt", multiline=True)
        
        if not prompt.strip():
            print_error("Prompt cannot be empty")
            pause()
            continue
        
        # Create agent spec
        spec = AgentSpec(
            domain=domain,
            action=action,
            object=obj,
            context={'prompt': prompt}
        )
        
        console.print()
        
        # Spawn agent
        try:
            with show_progress(f"Spawning agent {agent_name}...") as progress:
                progress.add_task("spawning", total=None)
                agent = factory.spawn(spec)
            
            print_success(f"Agent spawned: {agent_name}")
            print_key_value("Trace ID", format_trace_id(agent.trace_id))
            
            # Execute agent
            console.print()
            if not confirm(f"Execute {agent_name}?", default=True):
                continue
            
            console.print()
            with show_progress("Agent executing...") as progress:
                progress.add_task("executing", total=None)
                result = agent.run()
            
            # Display results
            console.print("\n" + "═" * 50 + "\n")
            
            if result.success:
                print_key_value("Duration", f"{result.duration_seconds:.2f}s")
                print_key_value("Iterations", result.iterations)
                
                console.print("\n[bold green]Result:[/bold green]\n")
                result_panel = Panel(
                    result.content if result.content else "[dim]No output[/dim]",
                    border_style="green",
                    title="Agent Output"
                )
                console.print(result_panel)
                
                print_success("Agent execution completed")
            else:
                print_error(f"Agent execution failed: {result.error}")
            
        except Exception as e:
            print_error(f"Agent spawn/execution failed: {str(e)}")
        
        pause()
        
        if not confirm("Spawn another agent?", default=False):
            break