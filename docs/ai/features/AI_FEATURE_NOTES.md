# AI FEATURE: NOTES
The Notes system is a flexible, Google Keep-style utility for capturing quick thoughts, structured lists, and time-bound reminders.

## 1. Note Architecture
The system supports two distinct note types:
- **Freeform Notes:** Standard text blocks for brainstorming or journaling.
- **Checklists:** Structured lists where each item has a `text` and a `done` (boolean) status.

## 2. Organization & Metadata
Notes are indexed and filtered using the following attributes:
- **Labels:** User-defined tags for categorization.
- **Pinning:** A `pinned` flag to keep high-priority notes at the top of the list.
- **Archiving:** A `archived` flag to remove notes from the main view without deleting them.
- **Colors:** Visual labels for quick scanning.

## 3. Reminder System
- **Scheduling:** Notes can be assigned a `due_date`.
- **Notification Pipeline:** The `manage_notes` tool integrates with the system's reminder dispatcher to alert the user.
- **AI-Synthesized Reminders:** For high-priority reminders, the system can use a lightweight LLM to transform a raw note title (e.g., "Buy Milk") into a "warm, motivating" notification (e.g., "Hey! Don't forget to grab some milk on your way home!").

## 4. AI Implementation Notes
When managing notes, the AI should:
1.  **Convert to Checklist:** If a user provides a list of items in a freeform note, suggest converting it to a `checklist` type for better tracking.
2.  **Auto-Label:** Suggest appropriate labels based on the content of the note.
3.  **Reminder Synthesis:** When creating reminders, offer to make them "motivating" if the user prefers a friendly tone.