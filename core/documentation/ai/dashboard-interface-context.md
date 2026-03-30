AETHVION SUITE - DASHBOARD INTERFACE CONTEXT
This document describes the tabs and features of the Aethvion Suite dashboard. For information about the assistant's specific tools and capabilities, refer to [assistant-tools.md](file:///c:/Aethvion/Aethvion-Suite/documentation/ai/assistant-tools.md).

TABS (format: tab_id | display name | description)

chat | Chat | Primary command interface. Multi-modal terminal for sending messages to the orchestrator or agents. Supports file attachments, prompt templates, tool and agent selection, and conversation threads. This is the main interaction hub.

misaka-cipher | Misaka Cipher | The direct chat interface with your core personality. Use this for private conversations, long-term memory updates, and managed companion interactions. [SwitchTab: misaka-cipher]

agent | Agent | Dedicated interface for spawning and monitoring autonomous agents. Users can start agents on specific tasks, observe their step-by-step execution, and view results. [SwitchTab: agent]

image | Image Studio | AI image generation workspace. Supports multi-model generation, image editing, upscaling, and expansion. [SwitchTab: image]

advaiconv | Advanced AI Conversation | Structured multi-agent conversation lab. [SwitchTab: advaiconv]

arena | LLM Arena | Model battle testing environment. [SwitchTab: arena]

aiconv | AI Conversation | Simplified two-party AI conversation mode. [SwitchTab: aiconv]

files | Files | Project file browser. [SwitchTab: files]

tools | Tools | Registry of all available tools and active agents. [SwitchTab: tools]

packages | Packages | Package manager interface. [SwitchTab: packages]

memory | Memory | Archive of all system memory. [SwitchTab: memory]

misaka-memory | Misaka Cipher Memory | Your specialized neural memory archive. Switch here when the user says "show me your memory". [SwitchTab: misaka-memory]

logs | Logs | Live log stream panel. [SwitchTab: logs]

usage | Usage | API usage analytics. [SwitchTab: usage]

status | Status | Live system status dashboard and changelog summaries. [SwitchTab: status]

finance | Finance | Personal financial tracking, portfolio, and AI market analysis. [SwitchTab: finance]

tracking | Tracking | Motion tracking bridge with HUD, telemetry, and FPS counter. [SwitchTab: tracking]

linkmap | LinkMap | Visual representation of tool and agent relationships. [SwitchTab: linkmap]

code | Code IDE | AI-powered development environment with streaming execution. [SwitchTab: code]

settings | Settings | Core configuration hub. The "Misaka Cipher" (previously Assistant) section allows for configuring the floating persona and individual chat models. [SwitchTab: settings]

TAB SWITCHING
If Dashboard Control is enabled in the assistant settings, the assistant can navigate the user to any tab.

Valid main tab IDs: chat, agent, image, advaiconv, arena, aiconv, files, tools, packages, memory, logs, usage, status, settings, misaka-cipher, misaka-memory, finance, tracking, linkmap, code

Valid subtab IDs (inside settings): assistant (labeled 'Misaka Cipher'), system, env, providers, profiles

Only use navigation when the user EXPLICITLY asks to navigate.
o somewhere or when it would be clearly helpful (e.g. "Where do I set my API keys?" -> [SwitchSubTab: providers]).
