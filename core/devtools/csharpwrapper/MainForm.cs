using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace AethvionSuite;

/// <summary>
/// Lightweight WebView2 wrapper for Aethvion Suite.
///
/// Flow
/// ────
///   1. Locate the project root (searches upward for Start_Aethvion.bat).
///   2. Verify the venv exists; show setup instructions if not.
///   3. Spawn pythonw.exe core\launcher.py --consumer --browser none.
///   4. Poll data/system/ports.json until the dashboard port appears,
///      falling back to probing 8080-8089 via HTTP.
///   5. Initialize WebView2 and navigate to the dashboard.
///   6. On close, kill the launcher and its entire process tree.
/// </summary>
public sealed class MainForm : Form
{
    // ── Branding ───────────────────────────────────────────────────────────────
    private const string AppName    = "Aethvion Suite";
    private const int    BasePort   = 8080;
    private const int    PortRange  = 10;           // probe 8080-8089

    // Timeouts & cadence
    private const int PollMs        = 600;          // interval between port checks
    private const int TimeoutMs     = 45_000;       // give up after 45 s

    // Colours matching the dashboard CSS
    private static readonly Color ColBg      = Color.FromArgb(15,  17,  23);   // --bg-primary  #0f1117
    private static readonly Color ColSurface = Color.FromArgb(17,  19,  28);   // card bg
    private static readonly Color ColText    = Color.FromArgb(226, 232, 240);  // --text-primary #e2e8f0
    private static readonly Color ColMuted   = Color.FromArgb(100, 116, 139);  // --text-muted   #64748b
    private static readonly Color ColAccent  = Color.FromArgb(34,  211, 238);  // cyan accent

    // ── State ──────────────────────────────────────────────────────────────────
    private readonly string _projectRoot;
    private Process?        _launcher;
    private WebView2?       _webView;

    // Splash-screen controls (kept as fields for SetStatus updates)
    private Label   _statusLabel  = null!;
    private Label   _dotLabel     = null!;
    private Button  _retryButton  = null!;
    private Panel   _splashPanel  = null!;
    private System.Windows.Forms.Timer _dotTimer = null!;
    private int     _dotFrame     = 0;

    // ── Constructor ────────────────────────────────────────────────────────────
    public MainForm()
    {
        _projectRoot = FindProjectRoot();

        // Window chrome
        Text            = AppName;
        Size            = new Size(1400, 900);
        MinimumSize     = new Size(960, 640);
        StartPosition   = FormStartPosition.CenterScreen;
        BackColor       = ColBg;
        Icon            = TryLoadIcon();

        BuildSplash();
    }

    // ── Splash screen ──────────────────────────────────────────────────────────
    private void BuildSplash()
    {
        _splashPanel = new Panel { Dock = DockStyle.Fill, BackColor = ColBg };

        // ── Centre container ──
        var centre = new Panel { AutoSize = true, BackColor = ColBg };

        // Logo / title
        var title = new Label
        {
            Text      = AppName,
            Font      = new Font("Segoe UI Light", 28f, FontStyle.Regular, GraphicsUnit.Point),
            ForeColor = ColText,
            AutoSize  = true,
        };

        // Animated dots
        _dotLabel = new Label
        {
            Text      = "   ",
            Font      = new Font("Segoe UI", 18f, FontStyle.Regular, GraphicsUnit.Point),
            ForeColor = ColAccent,
            AutoSize  = true,
            Padding   = new Padding(0, 2, 0, 8),
        };

        // Status message
        _statusLabel = new Label
        {
            Text      = "Initialising…",
            Font      = new Font("Segoe UI", 10f, FontStyle.Regular, GraphicsUnit.Point),
            ForeColor = ColMuted,
            AutoSize  = true,
        };

        // Retry / setup button (hidden until needed)
        _retryButton = new Button
        {
            Text      = "Retry",
            Font      = new Font("Segoe UI", 10f, FontStyle.Regular, GraphicsUnit.Point),
            ForeColor = ColText,
            BackColor = Color.FromArgb(30, 34, 50),
            FlatStyle = FlatStyle.Flat,
            AutoSize  = true,
            Padding   = new Padding(18, 6, 18, 6),
            Visible   = false,
        };
        _retryButton.FlatAppearance.BorderColor = Color.FromArgb(60, 70, 90);
        _retryButton.FlatAppearance.MouseOverBackColor = Color.FromArgb(40, 44, 62);
        _retryButton.Click += (_, _) => RestartFromScratch();

        // Stack them vertically, centred
        var flow = new FlowLayoutPanel
        {
            FlowDirection = FlowDirection.TopDown,
            AutoSize      = true,
            WrapContents  = false,
            BackColor     = ColBg,
            Padding       = new Padding(0),
        };
        foreach (Control c in new Control[] { title, _dotLabel, _statusLabel, _retryButton })
        {
            c.Margin = new Padding(0, 0, 0, 6);
            flow.Controls.Add(c);
        }

        _splashPanel.Controls.Add(flow);
        _splashPanel.Resize += (_, _) =>
        {
            flow.Left = (_splashPanel.Width  - flow.Width)  / 2;
            flow.Top  = (_splashPanel.Height - flow.Height) / 2;
        };

        Controls.Add(_splashPanel);

        // Animated dot timer
        _dotTimer = new System.Windows.Forms.Timer { Interval = 420 };
        _dotTimer.Tick += (_, _) =>
        {
            _dotFrame = (_dotFrame + 1) % 4;
            _dotLabel.Text = _dotFrame switch
            {
                0 => "●  ",
                1 => "●●  ",
                2 => "●●● ",
                _ => "    ",
            };
        };
        _dotTimer.Start();
    }

    // ── Load — async startup sequence ─────────────────────────────────────────
    protected override async void OnLoad(EventArgs e)
    {
        base.OnLoad(e);
        await RunStartupAsync();
    }

    private async Task RunStartupAsync()
    {
        // Check the venv exists
        var pythonW = Path.Combine(_projectRoot, ".venv", "Scripts", "pythonw.exe");
        if (!File.Exists(pythonW))
        {
            ShowSetupRequired(pythonW);
            return;
        }

        // Launch the Python backend
        SetStatus("Launching Aethvion Suite backend…");
        if (!StartLauncher(pythonW))
        {
            ShowError("Could not start the launcher.\nCheck that core\\launcher.py exists.");
            return;
        }

        // Wait for the dashboard to be ready
        SetStatus("Waiting for dashboard…");
        int port = await DiscoverPortAsync();
        if (port < 0)
        {
            ShowError($"Dashboard did not respond within {TimeoutMs / 1000} seconds.\n" +
                       "Check data\\logs\\launcher.log for details.");
            return;
        }

        // Hand off to WebView2
        SetStatus("Loading…");
        await InitWebViewAsync($"http://localhost:{port}");
    }

    // ── Launcher ──────────────────────────────────────────────────────────────
    private bool StartLauncher(string pythonW)
    {
        var launcher = Path.Combine(_projectRoot, "core", "launcher.py");
        if (!File.Exists(launcher))
            return false;

        var psi = new ProcessStartInfo
        {
            FileName         = pythonW,
            // --browser none: we are the window, don't open an additional browser
            Arguments        = $"\"{launcher}\" --consumer --browser none",
            WorkingDirectory = _projectRoot,
            UseShellExecute  = false,
            CreateNoWindow   = true,
        };
        // Ensure the Python path is set correctly
        psi.Environment["PYTHONPATH"]    = _projectRoot;
        psi.Environment["PYTHONUNBUFFERED"] = "1";

        try
        {
            _launcher = Process.Start(psi);
            return _launcher != null;
        }
        catch
        {
            return false;
        }
    }

    // ── Port discovery ────────────────────────────────────────────────────────
    /// <summary>
    /// First tries reading data/system/ports.json (written by PortManager).
    /// Falls back to HTTP-probing localhost:8080-8089.
    /// </summary>
    private async Task<int> DiscoverPortAsync()
    {
        using var http    = new HttpClient { Timeout = TimeSpan.FromMilliseconds(800) };
        var       elapsed = 0;
        var       portsFile = Path.Combine(_projectRoot, "data", "system", "ports.json");

        while (elapsed < TimeoutMs)
        {
            // ── 1. Try ports.json ──
            int jsonPort = TryReadPortsJson(portsFile);
            if (jsonPort > 0)
            {
                // Confirm it actually responds
                if (await ProbeAsync(http, jsonPort))
                    return jsonPort;
            }

            // ── 2. Probe the expected range ──
            for (int p = BasePort; p < BasePort + PortRange; p++)
            {
                if (await ProbeAsync(http, p))
                    return p;
            }

            await Task.Delay(PollMs);
            elapsed += PollMs;
            int secs = elapsed / 1000;
            SetStatus($"Waiting for dashboard… ({secs}s)");
        }

        return -1;
    }

    private static int TryReadPortsJson(string path)
    {
        try
        {
            if (!File.Exists(path)) return -1;
            var json = File.ReadAllText(path);
            using var doc = JsonDocument.Parse(json);
            foreach (var prop in doc.RootElement.EnumerateObject())
            {
                // Value is the service name; key is the port number
                var val = prop.Value.GetString() ?? "";
                if (val.Contains("Dashboard", StringComparison.OrdinalIgnoreCase) ||
                    val.Contains("Nexus",     StringComparison.OrdinalIgnoreCase)  ||
                    val.Contains("Aethvion",  StringComparison.OrdinalIgnoreCase))
                {
                    if (int.TryParse(prop.Name, out int port))
                        return port;
                }
            }
        }
        catch { /* ports.json not yet written or malformed — fine */ }
        return -1;
    }

    private static async Task<bool> ProbeAsync(HttpClient http, int port)
    {
        try
        {
            var resp = await http.GetAsync($"http://localhost:{port}/");
            // Any non-5xx response means the server is up
            return (int)resp.StatusCode < 500;
        }
        catch { return false; }
    }

    // ── WebView2 initialisation ───────────────────────────────────────────────
    private async Task InitWebViewAsync(string url)
    {
        _webView = new WebView2 { Dock = DockStyle.Fill, Visible = false };
        Controls.Add(_webView);

        // Store WebView2 user data alongside app data so each machine has
        // its own profile; avoids permission issues in portable installs.
        var userDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "AethvionSuite", "WebView2Cache");

        var env = await CoreWebView2Environment.CreateAsync(
            browserExecutableFolder: null,
            userDataFolder: userDataDir);

        await _webView.EnsureCoreWebView2Async(env);

        // Strip browser chrome — this is an app window, not a browser
        var settings = _webView.CoreWebView2.Settings;
        settings.AreDefaultContextMenusEnabled  = false;
        settings.IsStatusBarEnabled             = false;
        settings.IsZoomControlEnabled           = false;
        settings.AreDevToolsEnabled             = true;   // Ctrl+Shift+I still works

        // Show the window once the first page finishes loading
        _webView.CoreWebView2.NavigationCompleted += OnNavigationCompleted;
        _webView.CoreWebView2.Navigate(url);
    }

    private void OnNavigationCompleted(object? sender, CoreWebView2NavigationCompletedEventArgs e)
    {
        if (!e.IsSuccess) return;

        BeginInvoke(() =>
        {
            _dotTimer.Stop();
            _splashPanel.Visible = false;
            _webView!.Visible    = true;
            _webView.BringToFront();

            // Only fire once
            _webView.CoreWebView2.NavigationCompleted -= OnNavigationCompleted;
        });
    }

    // ── Error states ──────────────────────────────────────────────────────────
    private void ShowSetupRequired(string expectedPath)
    {
        SetStatus(
            $"Python virtual environment not found.\n\n" +
            $"Expected: {expectedPath}\n\n" +
            "Please run  Start_Aethvion.bat  first to install all dependencies,\n" +
            "then launch AethvionSuite.exe again.");
        ShowRetryButton("Open Start_Aethvion.bat", () =>
        {
            var bat = Path.Combine(_projectRoot, "Start_Aethvion.bat");
            if (File.Exists(bat))
                Process.Start(new ProcessStartInfo(bat) { UseShellExecute = true });
        });
    }

    private void ShowError(string message)
    {
        _dotTimer.Stop();
        _dotLabel.Visible = false;
        SetStatus(message);
        ShowRetryButton("Retry", RestartFromScratch);
    }

    private void ShowRetryButton(string text, Action action)
    {
        BeginInvoke(() =>
        {
            _retryButton.Text    = text;
            _retryButton.Visible = true;
            _retryButton.Click  += (_, _) => action();
        });
    }

    private void RestartFromScratch()
    {
        _retryButton.Visible = false;
        _dotLabel.Visible    = true;
        _dotTimer.Start();
        _ = RunStartupAsync();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    private void SetStatus(string message)
    {
        if (InvokeRequired)
            BeginInvoke(() => SetStatus(message));
        else
            _statusLabel.Text = message;
    }

    /// <summary>
    /// Walk parent directories starting from the .exe location until we find
    /// Start_Aethvion.bat — that directory is the project root.
    /// Falls back to the .exe directory itself (covers direct placement).
    ///
    /// NOTE: AppContext.BaseDirectory is NOT used here. With PublishSingleFile=true
    /// the runtime extracts bundles to a temp folder and BaseDirectory points there
    /// (e.g. %TEMP%\.net\AethvionSuite\...). Environment.ProcessPath always returns
    /// the real on-disk path of AethvionSuite.exe no matter where it is placed.
    /// </summary>
    private static string FindProjectRoot()
    {
        // Real path to AethvionSuite.exe on disk (not the temp extraction folder)
        var exeDir = Path.GetDirectoryName(Environment.ProcessPath)
                     ?? AppContext.BaseDirectory;

        var dir = new DirectoryInfo(exeDir);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "Start_Aethvion.bat")))
                return dir.FullName;
            dir = dir.Parent;
        }
        return exeDir;
    }

    private static Icon? TryLoadIcon()
    {
        // Look for icon.ico next to the real .exe (not the temp extraction folder)
        var exeDir = Path.GetDirectoryName(Environment.ProcessPath)
                     ?? AppContext.BaseDirectory;
        var path = Path.Combine(exeDir, "icon.ico");
        return File.Exists(path) ? new Icon(path) : null;
    }

    // ── Close ─────────────────────────────────────────────────────────────────
    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        _dotTimer.Stop();
        try
        {
            // Kill the entire Python process tree.
            // The launcher's Windows Job Object will cascade-kill all child
            // servers, so this single call is sufficient.
            if (_launcher != null && !_launcher.HasExited)
                _launcher.Kill(entireProcessTree: true);
        }
        catch { /* best-effort */ }

        _webView?.Dispose();
        base.OnFormClosing(e);
    }
}
