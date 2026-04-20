"""
Aethvion Suite - Professional Installer v10
════════════════════════════════════════════
Simple, clear language with active loading indicators and ultra-compact UI.
"""

import sys
import subprocess
import threading
import time
import re
import customtkinter as ctk
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk

# ── Windows Taskbar Fix ────────────────────────────────────────────────────────
# This MUST happen at the absolute top of the execution lifecycle.
if sys.platform == "win32":
    try:
        import ctypes
        myappid = 'com.aethvion.suite.installer.v14.final'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except: pass

# ── Theme ──────────────────────────────────────────────────────────────────────
BG_START    = "#0c0e14" 
BG_END      = "#1c2033" 
ACCENT      = "#6366f1"
SUCCESS     = "#10b981"
ERROR       = "#ef4444"
TEXT        = "#e2e8f0"
MUTED       = "#64748b"
BORDER      = "#2e364a"

class StepRow(ctk.CTkFrame):
    ICON_PENDING = "○"
    ICON_ACTIVE  = "›"
    ICON_DONE    = "✓"
    ICON_ERROR   = "✗"

    def __init__(self, master, title: str, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        
        self.icon_lbl = ctk.CTkLabel(self, text=self.ICON_PENDING, font=("Inter", 14), text_color=MUTED, width=15)
        self.icon_lbl.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.title_lbl = ctk.CTkLabel(self, text=title, font=("Inter", 12), text_color=MUTED, anchor="w")
        self.title_lbl.grid(row=0, column=1, sticky="w")

        self.bar = ctk.CTkProgressBar(self, height=4, width=100, progress_color=ACCENT, fg_color="#1e2330")
        self.bar.set(0)
        self.bar.grid(row=0, column=2, padx=10, sticky="ew")
        self.bar.grid_remove()

        self.pct_lbl = ctk.CTkLabel(self, text="", font=("Inter", 11, "bold"), text_color=MUTED, anchor="e", width=35)
        self.pct_lbl.grid(row=0, column=3, sticky="e")

        self.sub_lbl = ctk.CTkLabel(self, text="", font=("Inter", 10), text_color=MUTED, anchor="w", height=10)
        self.sub_lbl.grid(row=1, column=1, columnspan=3, sticky="nw")

    def set_active(self, sub: str = "", indeterminate=False):
        self.icon_lbl.configure(text=self.ICON_ACTIVE, text_color=ACCENT)
        self.title_lbl.configure(text_color=TEXT)
        self.pct_lbl.configure(text="..." if indeterminate else "0%", text_color=ACCENT)
        self.bar.grid()
        if indeterminate:
            self.bar.configure(mode="indeterminate")
            self.bar.start()
        else:
            self.bar.configure(mode="determinate")
            self.bar.set(0)
        if sub: self.sub_lbl.configure(text=sub)

    def set_progress(self, value: float, sub: str = ""):
        if self.bar.cget("mode") == "determinate":
            self.bar.set(value)
            self.pct_lbl.configure(text=f"{int(value * 100)}%")
        if sub: self.sub_lbl.configure(text=sub)

    def set_done(self):
        if self.bar.cget("mode") == "indeterminate":
            self.bar.stop()
            self.bar.configure(mode="determinate")
        self.bar.configure(progress_color=SUCCESS)
        self.bar.set(1.0)
        self.pct_lbl.configure(text="100%", text_color=SUCCESS)
        self.icon_lbl.configure(text=self.ICON_DONE, text_color=SUCCESS)
        self.title_lbl.configure(text_color=SUCCESS)
        self.sub_lbl.configure(text="")

    def set_error(self, msg: str = ""):
        if self.bar.cget("mode") == "indeterminate":
            self.bar.stop()
        self.bar.configure(progress_color=ERROR)
        self.icon_lbl.configure(text=self.ICON_ERROR, text_color=ERROR)
        self.title_lbl.configure(text_color=ERROR)
        if msg: self.sub_lbl.configure(text=msg, text_color=ERROR)

class AethvionInstaller(ctk.CTk):
    STEPS = [
        "Preparing Environment",
        "Scanning for Libraries",
        "Installing Libraries",
        "Setting up Folders",
        "Finalizing Installation",
    ]

    def __init__(self):
        super().__init__()
        self.project_root = Path(__file__).parent.parent.parent
        self.setup_dir    = self.project_root / "setup"
        self.logo_path    = self.project_root / "assets" / "aethvion" / "aethvion_logo.png"
        self.icon_path    = self.project_root / "assets" / "aethvion" / "aethvion_logov2.ico"

        # Window setup
        W, H = 540, 620
        self.title("Aethvion Suite Setup")
        
        # === Windows Taskbar & Title Bar Icon Fix ===
        if self.icon_path.exists():
            try:
                icon_abs = str(self.icon_path.resolve())
                
                # 1. Standard iconbitmap (for title bar)
                self.iconbitmap(icon_abs)
                self.wm_iconbitmap(icon_abs)
                
                # 2. Tkinter iconphoto (Stronger hint for taskbar)
                pil_icon = Image.open(icon_abs)
                self.tk_icon = ImageTk.PhotoImage(pil_icon)
                self.iconphoto(True, self.tk_icon)
                
            except Exception as e:
                print(f"[Icon Fix] Warning: {e}")

        self._center(W, H)
        self.resizable(False, False)
        
        self._create_gradient_bg(W, H)
        self._build_ui()
        self.after(500, self._start_install)

    def _center(self, w, h):
        self.geometry(f"{w}x{h}+{(self.winfo_screenwidth()-w)//2}+{(self.winfo_screenheight()-h)//2}")

    def _create_gradient_bg(self, w, h):
        img = Image.new("RGB", (w, h), BG_START)
        draw = ImageDraw.Draw(img)
        for i in range(h):
            r1, g1, b1 = int(BG_START[1:3], 16), int(BG_START[3:5], 16), int(BG_START[5:7], 16)
            r2, g2, b2 = int(BG_END[1:3], 16), int(BG_END[3:5], 16), int(BG_END[5:7], 16)
            r = int(r1 + (r2 - r1) * (i / h))
            g = int(g1 + (g2 - g1) * (i / h))
            b = int(b1 + (b2 - b1) * (i / h))
            draw.line([(0, i), (w, i)], fill=(r, g, b))
        self.bg_img = ctk.CTkImage(light_image=img, dark_image=img, size=(w, h))
        ctk.CTkLabel(self, image=self.bg_img, text="").place(x=0, y=0, relwidth=1, relheight=1)

    def _build_ui(self):
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=40, pady=(30, 20))

        # Header
        self.hdr = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.hdr.pack(fill="x")
        
        try:
            pil = Image.open(self.logo_path)
            ratio = 100 / pil.size[0]
            img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(100, int(pil.size[1] * ratio)))
            ctk.CTkLabel(self.hdr, image=img, text="").pack(anchor="center")
        except: pass

        self.title_lbl = ctk.CTkLabel(self.hdr, text="Aethvion Suite Setup", font=("Inter", 20, "bold"), text_color=TEXT)
        self.title_lbl.pack(pady=(10, 0))
        self.detail_lbl = ctk.CTkLabel(self.hdr, text="Preparing your local mission control dashboard", font=("Inter", 12), text_color=MUTED)
        self.detail_lbl.pack()

        # Step List
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent", height=160)
        self.scroll_frame.pack(fill="x", pady=(20, 10))

        self.step_rows = []
        for i, title in enumerate(self.STEPS):
            row = StepRow(self.scroll_frame, title)
            row.pack(fill="x", pady=1)
            self.step_rows.append(row)

        # Tech Log
        self.console_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.console_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.console_box = ctk.CTkTextbox(self.console_frame, fg_color="#080a0d", text_color="#10b981", font=("Consolas", 10), border_width=1, border_color=BORDER)
        self.console_box.pack(fill="both", expand=True)
        self.console_box.configure(state="disabled")

        # Launch Button
        self.launch_btn = ctk.CTkButton(self.main_frame, text="LAUNCH AETHVION SUITE", font=("Inter", 14, "bold"), height=50, fg_color=SUCCESS, hover_color="#059669", command=self._launch)

    def log(self, text):
        self.console_box.configure(state="normal")
        self.console_box.insert("end", f"› {text.strip()}\n")
        self.console_box.see("end")
        self.console_box.configure(state="disabled")

    def _ui(self, fn): self.after(0, fn)
    def _step_active(self, idx, sub="", indeterminate=False): self._ui(lambda: self.step_rows[idx].set_active(sub, indeterminate))
    def _step_progress(self, idx, val, sub=""): self._ui(lambda: self.step_rows[idx].set_progress(val, sub))
    def _step_done(self, idx): self._ui(lambda: self.step_rows[idx].set_done())
    def _step_error(self, idx, msg=""): self._ui(lambda: self.step_rows[idx].set_error(msg))

    def _start_install(self): threading.Thread(target=self._install_thread, daemon=True).start()

    def _install_thread(self):
        try:
            # 1. Computer Check
            self.log("[System] Checking local system resources...")
            self._step_active(0, "Verifying Python environment...")
            venv = self.project_root / ".venv"
            if not venv.exists():
                self.log("[Setup] Initializing virtual workspace")
                subprocess.run(["python", "-m", "venv", str(venv)], creationflags=subprocess.CREATE_NO_WINDOW)
            subprocess.run([str(venv/"Scripts"/"python.exe"), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], creationflags=subprocess.CREATE_NO_WINDOW)
            self._step_done(0)

            # 2. Scanning
            self._step_active(1, "Counting required libraries...")
            self._phase_pip(1, 2) # Handles both 1 and 2

            # 4. Folders
            self.log("[System] Creating data and project folders...")
            self._step_active(3, "Structuring project directories...")
            subprocess.run(["cmd", "/c", str(self.setup_dir/"setup_directories.bat")], creationflags=subprocess.CREATE_NO_WINDOW)
            self._step_done(3)

            # 5. Finishing
            self.log("[System] Finalizing your dashboard...")
            self._step_active(4, "Saving settings...")
            time.sleep(1)
            self._step_done(4)
            
            self.log("[Success] Installation is finished.")
            self._ui(self._show_success)
        except Exception as e:
            self.log(f"[Error] Installation failed: {e}")

    def _phase_pip(self, s1, s2):
        self.log("[System] Scanning library requirements...")
        pip_exe = str(self.project_root/".venv"/"Scripts"/"pip.exe")
        
        proc = subprocess.Popen([pip_exe, "install", "-e", ".[memory]", "--no-color", "--progress-bar", "off"], cwd=str(self.project_root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
        
        discovered_pkgs = []
        installed_count = 0
        current_phase = 1 
        
        for line in iter(proc.stdout.readline, ""):
            line = line.strip()
            if not line: continue
            self.log(line)

            if "Collecting" in line:
                pkg_match = re.search(r"Collecting ([^\s;>=<!(]+)", line)
                if pkg_match:
                    pkg = pkg_match.group(1)
                    if pkg not in discovered_pkgs: discovered_pkgs.append(pkg)
                self._step_progress(s1, min(0.95, len(discovered_pkgs)/25), f"Found {len(discovered_pkgs)} library files...")
            
            elif "Installing collected packages" in line:
                current_phase = 2
                self._step_done(s1)
                # Activate Step 3 with Indeterminate bar (loading icon style)
                self._step_active(s2, "Installing libraries, this might take a while...", indeterminate=True)
                
                # Parse total if possible
                pkgs_match = line.split("Installing collected packages:")
                if len(pkgs_match) > 1:
                    list_pkgs = [p.strip() for p in pkgs_match[1].split(",") if p.strip()]
                    if len(list_pkgs) > 5: discovered_pkgs = list_pkgs

            elif current_phase == 2:
                if line.startswith("Installing"):
                    pkg = line.split("Installing")[-1].strip().split()[0]
                    self._step_progress(s2, 0, f"Installing {pkg}...")
                elif "Successfully installed" in line:
                    pkgs_done = re.split(r'[,\s]+', line.replace("Successfully installed", "").strip())
                    installed_count += len([p for p in pkgs_done if p])
                    self._step_progress(s2, 0, f"Installed {installed_count} of {len(discovered_pkgs)} libraries...")

        proc.wait()
        self._step_done(s1)
        self._step_done(s2)

    def _show_success(self):
        self.scroll_frame.pack_forget()
        self.detail_lbl.configure(text="Everything is ready. Your dashboard is now functional.", text_color=SUCCESS)
        self.launch_btn.pack(fill="x", pady=20)

    def _launch(self):
        subprocess.Popen([str(self.project_root/"Start_Aethvion.bat")], cwd=str(self.project_root), creationflags=subprocess.CREATE_NEW_CONSOLE)
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    AethvionInstaller().mainloop()
