"""
Aethvion Suite - Professional Graphical Installer
══════════════════════════════════════════════════
A refined, dark-themed installer for the Aethvion Suite framework.
Uses CustomTkinter for a premium native look and feel.
"""

import sys
import os
import subprocess
import threading
import time
import webbrowser
import customtkinter as ctk
from pathlib import Path

# Configuration
VERSION = "v14.0"
ACCENT_COLOR = "#6366f1"  # Indigo
BG_COLOR = "#0f1115"      # Deep Charcoal
SUCCESS_COLOR = "#10b981" # Emerald

class AethvionInstaller(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"Aethvion Suite {VERSION} - Installer")
        self.geometry("600x480")
        self.resizable(False, False)
        
        # UI Styling
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG_COLOR)

        # Paths
        self.project_root = Path(__file__).parent.parent.parent
        self.setup_dir = self.project_root / "setup"

        # State
        self.installing = False
        self.complete = False

        self._create_widgets()

    def _create_widgets(self):
        # ── Main Container ──────────────────────────────────────────────────
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=40, pady=40)

        # ── Logo / Header ──────────────────────────────────────────────────
        self.logo_label = ctk.CTkLabel(
            self.main_container, 
            text="✦", 
            font=("Inter", 72),
            text_color=ACCENT_COLOR
        )
        self.logo_label.pack(pady=(20, 0))

        self.title_label = ctk.CTkLabel(
            self.main_container, 
            text="AETHVION SUITE",
            font=("Inter", 24, "bold"),
            text_color="white"
        )
        self.title_label.pack()

        self.version_label = ctk.CTkLabel(
            self.main_container, 
            text=f"Professional Agentic Framework • {VERSION}",
            font=("Inter", 12),
            text_color="#94a3b8"
        )
        self.version_label.pack(pady=(0, 40))

        # ── Dynamic Content Area ──────────────────────────────────────────────
        self.content_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # WELCOME VIEW
        self.welcome_btn = ctk.CTkButton(
            self.content_frame,
            text="Install Aethvion Suite",
            font=("Inter", 14, "bold"),
            height=50,
            fg_color=ACCENT_COLOR,
            hover_color="#4f46e5",
            command=self.start_installation
        )
        self.welcome_btn.pack(pady=20)

        self.tagline = ctk.CTkLabel(
            self.content_frame,
            text="Architecting the future of objective-driven intelligence.",
            font=("Inter", 11, "italic"),
            text_color="#64748b"
        )
        self.tagline.pack()

        # ── Bottom Bar ────────────────────────────────────────────────────
        self.bottom_label = ctk.CTkLabel(
            self,
            text="© 2026 Aethvion. All rights reserved.",
            font=("Inter", 10),
            text_color="#334155"
        )
        self.bottom_label.pack(side="bottom", pady=10)

    def prepare_status_view(self):
        """Transition to status screen."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.status_label = ctk.CTkLabel(
            self.content_frame,
            text="Initializing deployment...",
            font=("Inter", 13),
            text_color="white"
        )
        self.status_label.pack(pady=(20, 10))

        self.progress_bar = ctk.CTkProgressBar(
            self.content_frame,
            width=400,
            height=12,
            progress_color=ACCENT_COLOR,
            fg_color="#1e293b"
        )
        self.progress_bar.pack(pady=10)
        self.progress_bar.set(0)

        self.step_label = ctk.CTkLabel(
            self.content_frame,
            text="Awaiting orchestrator...",
            font=("Inter", 11),
            text_color="#94a3b8"
        )
        self.step_label.pack()

    def update_status(self, text, progress, step_text):
        self.status_label.configure(text=text)
        self.progress_bar.set(progress)
        self.step_label.configure(text=step_text)
        self.update_idletasks()

    def start_installation(self):
        if self.installing: return
        self.installing = True
        self.prepare_status_view()
        
        # Start installation thread
        threading.Thread(target=self.run_install_logic, daemon=True).start()

    def run_script(self, script_name):
        """Safely run a batch script and wait for completion."""
        script_path = self.setup_dir / script_name
        if not script_path.exists():
            return False
            
        process = subprocess.Popen(
            [str(script_path)],
            cwd=str(self.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        process.wait()
        return process.returncode == 0

    def run_install_logic(self):
        try:
            # Step 1: Env
            self.after(0, lambda: self.update_status("Calibrating Environment", 0.1, "Setting up Python virtual environment..."))
            time.sleep(1) # Visual padding
            self.run_script("setup_environment.bat")

            # Step 2: Directories
            self.after(0, lambda: self.update_status("Building Core Foundations", 0.4, "Structuring project directories and data folders..."))
            time.sleep(1)
            self.run_script("setup_directories.bat")

            # Step 3: Latest
            self.after(0, lambda: self.update_status("Synchronizing Systems", 0.7, "Pulling latest assets and updating dependencies..."))
            time.sleep(1)
            self.run_script("update_to_latest.bat")

            # Step 4: Finalize
            self.after(0, lambda: self.update_status("Finalizing Neural Pathways", 0.9, "Cleaning up and preparing launch manifest..."))
            time.sleep(1.5)

            self.after(0, self.show_completion)

        except Exception as e:
            self.after(0, lambda: self.update_status("Deployment Error", 1.0, f"Error: {str(e)}"))

    def show_completion(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.complete = True
        self.logo_label.configure(text_color=SUCCESS_COLOR, text="✓")
        
        self.success_title = ctk.CTkLabel(
            self.content_frame,
            text="Installation Complete",
            font=("Inter", 20, "bold"),
            text_color=SUCCESS_COLOR
        )
        self.success_title.pack(pady=(10, 5))

        self.success_sub = ctk.CTkLabel(
            self.content_frame,
            text="Aethvion Suite is now ready for deployment.",
            font=("Inter", 12),
            text_color="#94a3b8"
        )
        self.success_sub.pack(pady=(0, 30))

        self.launch_btn = ctk.CTkButton(
            self.content_frame,
            text="Launch Dashboard",
            font=("Inter", 14, "bold"),
            height=50,
            fg_color=SUCCESS_COLOR,
            hover_color="#059669",
            command=self.launch_suite
        )
        self.launch_btn.pack()

    def launch_suite(self):
        # Open the dashboard URL and close installer
        webbrowser.open("http://localhost:8080")
        # Attempt to run the start script in background
        start_script = self.project_root / "Start_AethvionWeb.bat"
        if start_script.exists():
            subprocess.Popen([str(start_script)], cwd=str(self.project_root), creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = AethvionInstaller()
    app.mainloop()
