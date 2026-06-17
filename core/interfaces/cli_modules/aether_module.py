"""
Aethvion Suite - Aether Core Module
Direct AI interaction through Aether Core
"""

from core.interfaces.cli_modules.utils import (
    console, clear_screen, print_header, get_text_input,
    format_trace_id, print_success, print_error, print_key_value,
    confirm, show_progress
)
from core.aether_core import AetherCore, Request
from rich.panel import Panel


def aether_core_module(aether: AetherCore):
    """
    Interactive Aether Core chat interface.
    
    Args:
        aether: AetherCore instance
    """
    while True:
        clear_screen()
        print_header("Aether Core", "Direct AI Interaction")
        
        console.print("\n[bold cyan]Enter your prompt below:[/bold cyan]")
        console.print("[dim](Leave empty to return to main menu)[/dim]\n")
        
        prompt = get_text_input("Prompt", multiline=False)
        
        if not prompt.strip():
            break
        
        # Optional configuration
        console.print()
        use_custom = confirm("Configure temperature/max_tokens?", default=False)
        
        temperature = None
        max_tokens = None
        
        if use_custom:
            temp_str = get_text_input("Temperature (0.0-1.0)", default="0.7")
            tokens_str = get_text_input("Max Tokens", default="1000")
            
            try:
                temperature = float(temp_str)
                max_tokens = int(tokens_str)
            except ValueError:
                print_error("Invalid temperature or max_tokens, using defaults")
        
        from core.interfaces.cli_modules.settings_module import load_settings
        def _get_active_models():
            settings = load_settings()
            providers = settings.get("providers", {})
            available = []
            for prov_name, data in providers.items():
                if prov_name in ['default', 'fallback_order']: continue
                if data.get('active'):
                    available.append(f"{prov_name} (default)")
                    for m in data.get('models', []): available.append(f"{prov_name}/{m}")
            return available if available else ["google_ai (fallback)"]
        
        console.print()
        use_custom_model = confirm("Select specific model/provider?", default=False)
        selected_model = None
        if use_custom_model:
            models = _get_active_models()
            from core.interfaces.cli_modules.utils import print_menu, get_user_choice
            print_menu("Available Models", models, include_exit=True)
            c = get_user_choice(len(models))
            if c > 0:
                selected_model = models[c-1]
                # Strip (default) if present
                selected_model = selected_model.replace(" (default)", "")
                
        # Send request
        console.print()
        with show_progress("Sending request to Aether Core...") as progress:
            progress.add_task("processing", total=None)
            
            # Pass model directly; Request.model overrides Aether router default
            request = Request(
                prompt=prompt,
                request_type="generation",
                temperature=temperature,
                max_tokens=max_tokens,
                model=selected_model if selected_model else None,
            )
            
            response = aether.route_request(request)
        
        # Display response
        console.print("\n" + "═" * 50 + "\n")
        
        if response.success:
            # Metadata
            print_key_value("Trace ID", format_trace_id(response.trace_id))
            print_key_value("Provider", response.provider)
            print_key_value("Firewall Status", response.firewall_status)
            print_key_value("Routing Decision", response.routing_decision)
            
            # Response content
            console.print("\n[bold green]Response:[/bold green]\n")
            
            # Use Panel for clean formatting
            response_panel = Panel(
                response.content,
                border_style="green",
                title="AI Response"
            )
            console.print(response_panel)
            
            print_success("Request completed successfully")
        else:
            print_key_value("Trace ID", format_trace_id(response.trace_id))
            print_error(f"Request failed: {response.error}")
        
        console.print()
        if not confirm("Send another request?", default=True):
            break