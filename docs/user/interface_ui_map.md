# Odysseus UI Map

This document maps every visual element of the Odysseus interface to its corresponding backend function or system tool.

## 1. The Navigation Rail (Far Left)
The rail provides global access to core system modules.

| Element | ID | Function / Tool | Description |
| :--- | :--- | :--- | :--- |
| New Chat Button | `#rail-new-session` | `sessionModule.newSession()` | Starts a fresh conversation session. |
| Chat History | `#rail-chats` | `sessionModule.listSessions()` | Accesses previous conversations. |
| Memory Tool | `#tool-memory-btn` | `memoryModule.open()` | Opens the Brain/Memory management modal. |
| Gallery Tool | `#tool-gallery-btn` | `galleryModule.open()` | Opens the image/asset gallery. |
| Cookbook Tool | `#tool-cookbook-btn` | `cookbookModule.open()` | Opens the model server management (Cookbook). |
| Doc Library | `#tool-doclib-btn` | `doclibModule.open()` | Opens the system documentation library. |
| Tasks Tool | `#tool-tasks-btn` | `tasksModule.open()` | Opens the task tracking panel. |
| Calendar Tool | `#tool-calendar-btn` | `calendarModule.open()` | Opens the calendar interface. |
| Notes Tool | `#tool-notes-btn` | `notesModule.open()` | Opens the persistent notes panel. |
| Library Tool | `#tool-library-btn` | `libraryModule.open()` | Opens the file/document library. |

## 2. The Sidebar (Left)
The sidebar handles session management and high-level system settings.

| Element | ID | Function / Tool | Description |
| :--- | :--- | :--- | :--- |
| Sidebar Toggle | `#sidebar-toggle-btn` | UI State Toggle | Collapses/Expands the sidebar. |
| Resize Handle | `#sidebar-resize-handle` | UI State Change | Adjusts the width of the sidebar. |
| Archive Button | `#tool-archive-btn` | `sessionModule.archive()` | Moves current session to archives. |
| Theme Button | `#tool-theme-btn` | `themeModule.open()` | Opens the appearance/theme customization modal. |
| Session Meta | `#current-meta` | `sessionModule.rename()` | Clicking the session name allows renaming via modal. |

## 3. The Chat Interface (Center/Right)
The primary interaction area for communicating with the AI.

| Element | ID | Function / Tool | Description |
| :--- | :--- | :--- | :--- |
| Chat History | `#chat-history` | UI Container | The scrollable area where messages are rendered. |
| Message Input | `#message-input` | `chatModule.handleChatSubmit` | The textarea for typing prompts. |
| Send Button | `#send-btn` | `chatModule.handleSubmit` | Triggers the submission of the current prompt. |
| Plus Button | `#plus-btn` | UI Overflow | Opens the "Plus" menu for additional tools/options. |
| Mode Toggle | `#mode-toggle` | `setMode('chat'/'agent')` | Switches between standard chat and agentic mode. |
| Bash Toggle | `#bash-toggle` | `bashModule.toggle()` | Enables/Disables direct bash execution. |
| Research Toggle| `#research-toggle-btn` | `researchModule.toggle()` | Activates research mode. |
| Plan Button | `#plan-btn` | `planModule.toggle()` | Opens/Closes the active plan window. |
| Incognito Btn | `#incognito-btn` | `sessionModule.toggleIncognito()`| Toggles private session mode. |

## 4. Modals & Overlays
Deep-dive interfaces for specific system configurations.

| Modal ID | Primary Purpose | Key Controls |
| :--- | :--- | :--- |
| `#memory-modal` | Brain Management | Memory Search, Skill Addition, Context Toggles. |
| `#theme-modal` | Appearance | Color Pickers, Theme Presets, Frosted Glass Toggle. |
| `#cookbook-modal`| Server Management | Model Serving, VLLM/Ollama controls. |
| `#settings-modal` | Global Config | User Account, API Keys, System Preferences. |
| `#rename-session-modal` | Session Naming | Input field to change the current session title. |
| `#custom-preset-modal`| Theme Creation | Interface for saving a custom color scheme. |

## 5. Hidden UX & Shortcuts
Features that are not explicitly labeled with buttons.

| Trigger | Action | Effect |
| :--- | :--- | :--- |
| `Enter` | Submit | Sends the message in the input box. |
| `Shift + Enter`| Newline | Adds a line break to the message. |
| `Escape` | Close | Closes the currently open modal or dropdown menu. |
| `Click Session Name`| Rename | Triggers the session rename workflow. |
| `Input Change` | Auto-hide Picker | Hides the model picker once $\ge 10$ characters are typed. |