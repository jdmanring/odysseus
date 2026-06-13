# AI FEATURE TASKS

The Task system is Odysseus's background automation engine. it enables the agent to move from a reactive chat interface to a proactive assistant by executing scheduled or event-driven logic without user intervention.

## 1. Core Architecture: The TaskScheduler

The `TaskScheduler` (`src/task_scheduler.py`) is the heartbeat of the system. It manages the transition from "due" to "executing."

### The Serial Execution Guarantee
To prevent resource contention and race conditions (especially when tasks modify the same memory or files), the system enforces a **hard serial execution limit**:
- **Semaphore(1):** Only one task can run at any given time. 
- **Queueing:** Any task triggered while another is running is placed in a queue and starts immediately upon the completion of the previous task.

### Singleflight TTL Cache
To optimize performance when multiple tasks fire simultaneously (e.g., a midnight cleanup of both sessions and documents), the scheduler implements a `_shared_cache`. 
- **Deduplication:** If two tasks request the same external data (e.g., a specific API snapshot) within the same TTL window, the second task awaits the result of the first instead of triggering a redundant network call.

---

## 2. Scheduling Logic

Tasks can be triggered in three primary ways:

### A. Time-Based (Scheduled)
The system supports several wall-clock patterns, all normalized to UTC for database storage:
- **Cron:** Full `croniter` support for complex schedules (e.g., `0 */2 * * *` for every 2 hours).
- **Daily/Weekly/Monthly:** Simple frequency settings based on a specified time (HH:MM).
- **Once:** A one-time execution at a specific timestamp.
- **Timezone Intelligence:** If a task is linked to a `CrewMember`, it uses that member's IANA timezone to calculate "local" wall-clock time before converting to UTC.

### B. Event-Driven
Tasks can be bound to specific system events. When the event fires, the task is queued:
- `session_created` $\rightarrow$ (e.g., Tidy Chat Sessions)
- `document_created` $\rightarrow$ (e.g., Documents Tidy)
- `memory_added` $\rightarrow$ (e.g., Memory Tidy)
- `research_completed` $\rightarrow$ (e.g., Research Tidy)

### C. Manual Trigger
The agent or user can manually trigger a task via the API (`/api/tasks/{id}/trigger`).

---

## 3. Task Types & Housekeeping

### Housekeeping Defaults
Every user is automatically seeded with "Housekeeping" tasks. These are the system's self-maintenance routines:
- **Tidy Sessions/Documents/Research:** Cleans up orphaned or stale data.
- **Consolidate Memory:** Merges duplicate memories to maintain a lean vector index.
- **Email Triage:** Periodically checks for urgency and tags emails.
- **Skills Audit:** Reviews added skills to ensure consistency.

### User-Defined Tasks
Users can create custom tasks that execute specific **Actions**. These actions are validated for security (e.g., `shell` or `python` actions are restricted to administrators).

---

## 4. Execution Lifecycle

1.  **Polling:** The scheduler loop checks the DB for `active` tasks where `next_run <= now`.
2.  **Dispatch:** The task enters the `_run_semaphore` queue.
3.  **Execution:** The `action` is executed (e.g., a Python function or a shell script).
4.  **Persistence:**
    - A `TaskRun` record is created to track the `started_at`, `finished_at`, `status` (success/error/aborted), and the `result` text.
    - If the output target is set to "notification," the result is pushed to the in-memory notification queue.
5.  **Reschedule:** The `compute_next_run` logic calculates the next execution date based on the schedule.

## 5. Recovery & Safety

- **Zombie Cleanup:** On server restart, any tasks stuck in `running` or `queued` are marked as `aborted`. This prevents the UI from showing "phantom" active tasks after a crash.
- **Overdue Push:** To prevent "firing storms" (where a server outage causes 1,000 tasks to be overdue), the system pushes the `next_run` of overdue tasks forward by 60 seconds on startup to stagger execution.
- **Auth Boundaries:** The `/api/tasks` endpoints strictly validate ownership. A user cannot trigger or view tasks belonging to another user.