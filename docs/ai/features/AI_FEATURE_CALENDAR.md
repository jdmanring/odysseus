# AI FEATURE: CALENDAR
The Calendar is a timezone-aware scheduling system that manages events, reminders, and recurring appointments. It serves as the system's "Temporal Memory."

## 1. Core Logic & Storage
- **Backend:** SQLite-backed storage for events.
- **Timezone Handling:** Integrates with the `user_time` service. Natural language inputs (e.g., "tomorrow at 9pm") are parsed in the user's local timezone and then converted to UTC for database storage.
- **Event Types:**
    - **Standard Events:** Specific start/end timestamps.
    - **All-Day Events:** Boolean flag `all_day` to bypass specific time constraints.

## 2. Recurrence Engine (Advanced)
The system supports complex recurring events using the `dateutil.rrule` library:
- **Expansion:** Recurring events are not stored as thousands of individual entries. Instead, a "Base Event" is stored with an RRULE string.
- **Occurrence Resolution:** When querying a date range, the system expands the RRULE to generate "virtual" occurrences.
- **Instance Overrides:** Individual occurrences of a recurring series can be modified or deleted. These are tracked via compound UIDs (`base_uid::date`), allowing the system to preserve the series while overriding a specific date.

## 3. Integration & Interop
- **ICS Support:** Full support for importing and exporting `.ics` files for compatibility with Google Calendar, Outlook, and Apple Calendar.
- **Reminders:** Integration with the `dispatch_reminder` system to fire notifications based on event lead times.

## 4. AI Implementation Notes
When managing the calendar, the AI should:
1.  **Verify Timezones:** Always confirm the user's current local time before scheduling "today" or "tomorrow" events.
2.  **Use RRULEs for Habits:** Instead of creating 10 separate events for a weekly meeting, create one recurring event.
3.  **Handle Conflicts:** Check for overlapping events before confirming a new appointment to the user.