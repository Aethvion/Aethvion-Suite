"""
Aethvion Suite - CLI Utilities
Shared utilities for CLI modules using rich library
"""

import os
import sys
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

# Global console instance
console = Console()


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str, subtitle: Optional[str] = None):
    """
    Print a formatted header.
    
    Args:
        title: Main title text
        subtitle: Optional subtitle
    """
    text = Text()
    text.append(title, style="bold cyan")
    
    if subtitle:
        text.append(f"\n{subtitle}", style="dim")
    
    console.print(Panel(text, box=box.DOUBLE, border_style="cyan"))


def print_banner():
    """Print the Aethvion Suite banner."""
    from rich.align import Align
    from rich.text import Text as RichText

    title = RichText(justify="center")
    title.append(" █████╗ ███████╗████████╗██╗  ██╗██╗   ██╗██╗ ██████╗ ███╗   ██╗\n", style="bold bright_cyan")
    title.append("██╔══██╗██╔════╝╚══██╔══╝██║  ██║██║   ██║██║██╔═══██╗████╗  ██║\n", style="bold bright_cyan")
    title.append("███████║█████╗     ██║   ███████║██║   ██║██║██║   ██║██╔██╗ ██║\n", style="bold bright_cyan")
    title.append("██╔══██║██╔══╝     ██║   ██╔══██║╚██╗ ██╔╝██║██║   ██║██║╚██╗██║\n", style="bold bright_cyan")
    title.append("██║  ██║███████╗   ██║   ██║  ██║ ╚████╔╝ ██║╚██████╔╝██║ ╚████║\n", style="bold bright_cyan")
    title.append("╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝  ╚═══╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝", style="bold bright_cyan")

    console.print(title)
    console.print(
        "Local AI Dashboard & Agentic Center",
        style="italic dim",
        justify="center"
    )
    console.print("Command Line Interface\n", style="bold cyan", justify="center")


def print_menu(title: str, options: List[str], include_exit: bool = True):
    """
    Print a numbered menu.
    
    Args:
        title: Menu title
        options: List of menu option strings
        include_exit: Whether to include Exit/Back option
    """
    table = Table(title=title, box=box.ROUNDED, show_header=False, border_style="cyan")
    table.add_column("Option", style="bold yellow", width=4)
    table.add_column("Description", style="white")
    
    for i, option in enumerate(options, 1):
        table.add_row(f"[{i}]", option)
    
    if include_exit:
        table.add_row("[0]", "← Back" if title != "Main Menu" else "Exit")
    
    console.print(table)


def get_user_choice(max_option: int, prompt_text: str = "Select option") -> int:
    """
    Get validated user menu choice.
    
    Args:
        max_option: Maximum valid option number
        prompt_text: Prompt message
        
    Returns:
        Selected option number (0 to max_option)
    """
    while True:
        try:
            choice = Prompt.ask(
                f"[bold yellow]{prompt_text}[/bold yellow]",
                default="0"
            )
            choice_num = int(choice)
            
            if 0 <= choice_num <= max_option:
                return choice_num
            else:
                console.print(
                    f"[red]Invalid option. Please enter 0-{max_option}[/red]"
                )
        except ValueError:
            console.print("[red]Invalid input. Please enter a number[/red]")
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled[/yellow]")
            return 0


def get_text_input(
    prompt_text: str,
    default: Optional[str] = None,
    multiline: bool = False
) -> str:
    """
    Get text input from user.
    
    Args:
        prompt_text: Prompt message
        default: Default value
        multiline: Whether to accept multiline input
        
    Returns:
        User input string
    """
    if multiline:
        console.print(f"[bold yellow]{prompt_text}[/bold yellow]")
        console.print("[dim](Press Ctrl+D or Ctrl+Z when done, or enter '###' on new line)[/dim]")
        
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "###":
                    break
                lines.append(line)
        except EOFError:
            pass
        
        return "\n".join(lines)
    else:
        return Prompt.ask(
            f"[bold yellow]{prompt_text}[/bold yellow]",
            default=default or ""
        )


def confirm(message: str, default: bool = False) -> bool:
    """
    Get yes/no confirmation from user.
    
    Args:
        message: Confirmation message
        default: Default value
        
    Returns:
        True if confirmed, False otherwise
    """
    return Confirm.ask(f"[bold yellow]{message}[/bold yellow]", default=default)


def print_success(message: str):
    """Print a success message."""
    console.print(f"✓ {message}", style="bold green")


def print_error(message: str):
    """Print an error message."""
    console.print(f"✗ {message}", style="bold red")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"⚠ {message}", style="bold yellow")


def print_info(message: str):
    """Print an info message."""
    console.print(f"ℹ {message}", style="bold blue")


def format_trace_id(trace_id: str) -> str:
    """
    Format a Trace_ID with highlighting.
    
    Args:
        trace_id: Trace ID string
        
    Returns:
        Formatted rich markup string
    """
    return f"[bold magenta]{trace_id}[/bold magenta]"


def print_trace_info(trace_id: str, details: Dict[str, Any]):
    """
    Print formatted Trace_ID information.
    
    Args:
        trace_id: Trace ID
        details: Dictionary of trace details
    """
    table = Table(
        title=f"Trace: {trace_id}",
        box=box.ROUNDED,
        border_style="magenta",
        show_header=False
    )
    table.add_column("Field", style="bold cyan")
    table.add_column("Value", style="white")
    
    for key, value in details.items():
        table.add_row(key, str(value))
    
    console.print(table)


def print_table(
    title: str,
    columns: List[str],
    rows: List[List[str]],
    highlight_col: Optional[int] = None
):
    """
    Print a formatted table.
    
    Args:
        title: Table title
        columns: Column headers
        rows: List of row data
        highlight_col: Column index to highlight (optional)
    """
    table = Table(title=title, box=box.ROUNDED, border_style="cyan")
    
    for i, col in enumerate(columns):
        style = "bold yellow" if i == highlight_col else "cyan"
        table.add_column(col, style=style)
    
    for row in rows:
        table.add_row(*row)
    
    console.print(table)


def show_progress(task_description: str):
    """
    Create a progress spinner context manager.
    
    Args:
        task_description: Description of task in progress
        
    Returns:
        Progress context manager
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    )


def print_divider():
    """Print a horizontal divider."""
    console.print("─" * console.width, style="dim")


def pause(message: str = "Press Enter to continue..."):
    """
    Pause and wait for user input.
    
    Args:
        message: Pause message
    """
    Prompt.ask(f"[dim]{message}[/dim]", default="")


def print_key_value(key: str, value: Any, key_style: str = "bold cyan"):
    """
    Print a key-value pair.
    
    Args:
        key: Key text
        value: Value to display
        key_style: Style for key
    """
    console.print(f"[{key_style}]{key}:[/{key_style}] {value}")
