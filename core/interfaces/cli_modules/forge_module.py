"""
Misaka Cipher - Forge Module
Tool generation interface
"""

from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, get_text_input,
    format_trace_id, print_success, print_error, print_warning,
    print_key_value, pause, show_progress, confirm
)
from core.forge import ToolForge
from rich.panel import Panel
from rich.syntax import Syntax


def forge_module(forge: ToolForge):
    """
    Interactive tool generation interface.
    
    Args:
        forge: ToolForge instance
    """
    while True:
        clear_screen()
        print_header("The Forge", "Autonomous Tool Generation")
        
        console.print("\n[bold cyan]Describe the tool you want to generate:[/bold cyan]")
        console.print("[dim]Be specific about what the tool should do[/dim]\n")
        
        description = get_text_input("Tool Description", multiline=True)
        
        if not description.strip():
            break
        
        # Optional implementation hints
        console.print()
        add_hints = confirm("Add implementation hints?", default=False)
        
        hints = {}
        if add_hints:
            console.print("\n[dim]Enter any specific implementation guidance (optional):[/dim]")
            hint_text = get_text_input("Hints", multiline=True)
            if hint_text.strip():
                hints = {'guidance': hint_text}
        
        # Generate tool
        console.print()
        try:
            with show_progress("Analyzing tool description...") as progress:
                task = progress.add_task("analyzing", total=None)
                
                progress.update(task, description="Generating code...")
                tool_info = forge.generate_tool(description, implementation_hints=hints)
                
                progress.update(task, description="Validating tool...")
            
            # Display results
            console.print("\n" + "═" * 50 + "\n")
            
            print_success("Tool generated successfully!")
            console.print()
            
            print_key_value("Tool Name", f"[bold green]{tool_info['name']}[/bold green]")
            print_key_value("Domain", tool_info['domain'])
            print_key_value("Description", tool_info['description'])
            print_key_value("Trace ID", format_trace_id(tool_info['trace_id']))
            print_key_value("File Path", tool_info['file_path'])
            print_key_value("Validation", "✓ Passed" if tool_info['validation_status'] == 'passed' else "✗ Failed")
            
            # Show parameters if any
            if tool_info.get('parameters'):
                console.print("\n[bold yellow]Parameters:[/bold yellow]")
                for param in tool_info['parameters']:
                    required = "required" if param.get('required') else "optional"
                    console.print(f"  • {param['name']} ({param['type']}) - {required}")
            
            # Offer to view code
            console.print()
            if confirm("View generated code?", default=False):
                try:
                    with open(tool_info['file_path'], 'r') as f:
                        code = f.read()
                    
                    console.print()
                    syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
                    console.print(syntax)
                except Exception as e:
                    print_warning(f"Could not read code: {str(e)}")
            
        except ValueError as e:
            console.print()
            print_error(f"Tool generation failed: {str(e)}")
            console.print("\n[dim]The tool may have failed validation checks.[/dim]")
            console.print("[dim]Try simplifying the description or removing risky operations.[/dim]")
        
        except Exception as e:
            console.print()
            print_error(f"Tool generation error: {str(e)}")
        
        pause()
        
        if not confirm("Generate another tool?", default=False):
            break