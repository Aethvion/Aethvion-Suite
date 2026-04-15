# Changelog

All notable changes to Aethvion Suite will be documented in this file.
The top section contains the latest changes that are already available on the `main` branch.

## [Unreleased] / In Development

### Major Feature Set Expansion (WIP)
- **Incognito Chat Mode:** Private sessions with fully ephemeral threads that wipe all data from memory on exit, bypass persistence, and force no-context mode.
- **Hide Sidebar:** Added a new "Full Hide" control to the sidebar header to maximize workspace layout for focused work.
- **3D Models Hub:** A new dedicated tab in the Model Hub featuring state-of-the-art 3D generation models (Trellis 2, TripoSR, CRM) with local generation and export controls.

### Major Agent Improvements
- Real token-level streaming with live thinking display
- Automatic error recovery loop with intelligent repair passes
- Dynamic replanning when steps fail or produce unexpected results
- Robust file editing with diff preview panel and undo/restore functionality
- Significantly improved context handling and tool usage
- Better shell command output (line-by-line streaming with configurable timeout per command)
- Enhanced web fetching for cleaner article and documentation content
- New Agent performance dashboard (token usage, success rate, and average task duration)

### Other Improvements
- Various stability and quality improvements across the agent system

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