# Changelog

All notable changes to Aethvion Suite will be documented in this file.

## [v16] - 2026-05-24

### Major Additions
- **Automate**: Entirely new node-based visual workflow builder — drag-and-drop canvas with wires, a full node inspector, real-time execution results, and auto-saving. Ships with 40+ nodes across categories: triggers, AI, data, file, screen capture, web, notifications, and more.
- **AethvionDB**: New dedicated knowledge database system — distill and store structured entity data from any source. Includes a file explorer, interactive graph view, vector embeddings, semantic search, baked snapshots, import support, an API page, a validator with auto-fix, and a full CRUD editor.
- **WorldSim**: New world simulation environment added to the suite.
- **Games — New Additions**: Code Gold and Debug This games added. Arena gains a full Gauntlet mode with improved result display and a shared model selector.
- **Companions — Dedicated Tab**: Companions are now their own top-level navigation tab. Major rework with a unified engine, a new memory tab, collapsible sidemenu, expressions system, icon in sidebar, and improved companion creator.
- **C# WebView2 Wrapper**: Native lightweight `.exe` launcher for Aethvion Suite. Provides a proper application window without needing a browser. Self-contained, no .NET runtime required on the target machine.

### Major Improvements
- **Automate — Node Library Expansion**: Nodes added iteratively across the update cycle — 6 + 6 + 7 + 9 + 10 more batches, plus specialized nodes: OCR Text Extraction, AethvionDB Search, AethvionDB Snapshot Search, screenshot node, display node, and path selector.
- **Automate — UX Polish**: Input nodes are color-coded by type and show a live character preview of their content. Output connection points moved to the outer edge of cards so wires no longer travel inside nodes. Inspector redesigned. Camera position and zoom saved per workflow and restored on load. Results hover-link to the responsible canvas node. Copy button added to result cards. Text in result cards is now selectable.
- **Automate — Workflow Management**: Import and export workflows as JSON files. Reset view button added to the toolbar.
- **Automate — AethvionDB Integration**: AethvionDB Search (raw entities) and AethvionDB Snapshot Search (baked datasets) nodes with a database dropdown selector and a `speed` output port showing search time in ms.
- **Code IDE (renamed from Agents)**: Renamed and restructured. Now shows created files and supports search across the project. Added revert options with improved stability, better security model, and autosaving. Better file explorer layout.
- **AethvionDB — Graph**: Fixed graph focus, added back button, expanded and deepened graph view, better highlight on hover, more detailed node info panel, and fixed graph resetting on re-entry.
- **AethvionDB — Validation**: Improved validator scans for soft-removed files, auto-fixes integrity errors, fixes `~-` date formats, and shows timeline fix summaries.
- **AethvionDB — Vector & Semantic Search**: Added vector embedding support with embedding info in the explorer. Full semantic search using embeddings. Parallel distilling for faster processing.
- **AethvionDB — Explorer & API**: Improved database explorer with a table-format file view, richer metadata (file size, dates), databases tab with fixed default path, import support, and an API page with dedicated API endpoints.
- **Startup & Shutdown**: Startup screen redesigned with better visual feedback. Shutdown sequence improved for cleaner exits. Launcher stability improved with a package health check on every boot.
- **Chat**: Smooth scroll with fade-in on new messages, lerped cursor for less jitter, fixed internet search, clearer task detail display.
- **Companions**: Fixed multi-reply, tool use, expression consistency on refresh, markdown rendering, and sidemenu ordering.
- **AI → Home Merge**: The AI tab has been merged into the Home tab for a cleaner navigation structure.
- **Header & UX**: Updated header apps bar, improved page transitions, better overall UX consistency.
- **Local Models**: Significantly improved load times. Added support for installing `llama-cpp-python` directly from the UI.
- **Explained**: Added edit mode and creation details view.
- **Smart Chunks**: Added Smart Chunks to the Tools section.
- **Sidemenu**: Improved search functionality.

### Fixes
- Output connection dots rendering inside cards instead of on the outside edge
- Extract JSON node crashing on bracket notation paths (e.g. `[0].name`)
- Tab loading delay on Home, Chat, AI, and AethvionDB
- Reloading snapping back to the wrong page
- Apps (LinkMap, Photo Studio, VTuber) failing to launch
- Chat and AethvionDB not refreshing correctly
- Companion creator not working
- AethvionDB graph resetting on every re-entry
- Old routes pointing to Nexus instead of the new structure
- Package repair not running when launching via `.bat` file

### How to Update
- Use the built-in **self-update** button in **Settings → Version Control**
- Or run `git pull` if you're using the git version

---

## [v15] - 2026-04-20

### Major Additions
- **Incognito Chat Mode**: Private sessions with fully ephemeral threads that automatically wipe all data from memory on exit and bypass persistence.
- **Custom Graphical Installer**: Replaced the raw CMD installer with a clean, modern Aethvion-branded installer for a much better first-time experience.
- **Running Services Panel**: New panel to monitor and manage heavier local model servers (e.g. Trellis 2, TripoSR) running in their own isolated environments.
- **3D Models Hub & Workspace**: Dedicated section for downloading and generating 3D models locally using models like Trellis 2 and TripoSR, with export controls.

### Major Improvements
- **Agents**: Massive upgrade including token-level streaming with live thinking, automatic error recovery with repair passes, dynamic replanning, robust file editing with diff preview + undo/restore, better context handling, line-by-line shell output, improved web fetching, and a new performance dashboard.
- **Companions**: Complete rework — now fully dynamic with a unified companion engine. All companions (including custom ones) use the same backend.
- **Local Models**: Major overhaul — much cleaner UI and better organization.
- **Performance**: Significant backend improvements. Inactive tabs and non-visible panels now consume near-zero resources.
- **Data Structure**: Restructured `/data/` directories for better organization and clarity.
- **Model Registry**: Full rework with proper separation of defaults and suggested models. New users now get sensible defaults on first install.
- **Sidebar**: Now supports full hide mode and improved bottom section layout (2x2 grid).
- **Chat & Companions**: Token-level streaming everywhere + automatic thread creation when submitting a prompt with no active thread.
- **Settings**: Major UI overhaul with much better logic and user experience.
- **UX Consistency**: Large number of small improvements across all pages for a more polished and professional feel.
- **Styling & Code**: Fixed broken/default styling, cleaned up CSS and code throughout the project.
- **Desktop Overlay**: Removed the weird double border.

### Fixes
- Chat threads scrollbar flickering in empty threads
- Sidemenu missing tabs on preconfigured profiles (now shows all options correctly)
- Model selector not loading options on refresh
- Agents scrolling issues when switching/loading pages
- Many smaller stability and visual fixes

### How to Update
- Use the built-in **self-update** button in **Settings → Version Control**
- Or run `git pull` if you're using the git version

---

## [v14] - 2026-04-14

### Major UX Overhaul
- Fully dynamic sidebar with user-created profiles (Work, Leisure, Creative Studio, Companion Hub, etc.)
- Easy profile switching, customization, drag & drop reordering
- Complete Home page redesign — now a proper Mission Control dashboard
- Smooth panel transition animations and faster navigation
- Standardized panel headers, improved empty states, button animations, and consistent scrollbars across the app
- Chat now persists selected model after refresh/load

### Other Changes
- Chat: Added resend message, regenerate response, and copy options
- Code blocks in chat now include convenient copy buttons
- Many small UI fixes and polish

### How to Update
- Use the built-in **self-update** button in **Settings → Version Control**
- Or run `git pull` if you're using the git version

## [v13] and earlier
- Early development versions with rapid internal changes
- Initial implementation of agent workspaces, hybrid cloud + local support, and basic dashboard
- Everything is now significantly more polished and professional

*Older versions (v1 through v13) had very rapid internal development and are not fully documented here.*