# AI FEATURE DEEP RESEARCH

Deep Research is an iterative, LLM-in-the-loop system designed to gather, read, and synthesize information from the web into a comprehensive visual report. Unlike a simple search, it employs a multi-step reasoning loop to explore a topic deeply.

## 1. The Research Lifecycle

Deep Research follows a structured pipeline: **Synthesis $\rightarrow$ Planning $\rightarrow$ Iterative Execution $\rightarrow$ Final Synthesis**.

### Phase 1: Query Synthesis
The system does not simply research the last user message. It analyzes the entire session history to synthesize a focused, specific research query. 
- **Context Awareness:** It captures user preferences, constraints, and prior clarifications.
- **Affirmation Handling:** It recognizes when a user says "yes" or "proceed" to a suggested plan and refers back to the original substantive request.

### Phase 2: Planning
Before searching, the system generates a **Research Plan**:
- **Sub-questions:** Breaks the main query into smaller, researchable questions.
- **Key Topics:** Identifies core areas that must be covered.
- **Success Criteria:** Defines what a "complete" answer looks like.
- **User Review:** This plan can be presented to the user for approval or modification before execution.

### Phase 3: Iterative Execution (The Loop)
The core engine (based on IterResearch) runs an autonomous loop:
1. **Search:** Generates search queries based on the plan and current findings.
2. **Read & Extract:** Fetches web pages and extracts relevant "findings" (factual snippets).
3. **Update Report:** Updates an **Evolving Report** in real-time.
4. **Evaluate:** The LLM decides if the success criteria have been met. If not, it generates new queries to fill the gaps and repeats the loop.

### Phase 4: Final Synthesis
Once the loop terminates (or hits a limit), the evolving report is polished into a final visual report with structured sections and cited sources.

---

## 2. Technical Implementation

### Task Registry & Persistence
Research runs as a background `asyncio.Task` to ensure the UI remains responsive.
- **Persistence:** All results, progress, and sources are saved to `data/deep_research/{session_id}.json`.
- **Resilience:** If the user refreshes the page, the system recovers the task state from disk.
- **Partial Results:** In the event of a crash or timeout, the "evolving report" is saved as a partial result so the user doesn't lose the work already done.

### Resource Management
To prevent infinite loops or system hangs:
- **`max_rounds`:** A hard cap on the number of iterations (default 20).
- **Wall-Clock Timeout:** A global timeout (configured in `settings.json` as `research_run_timeout_seconds`) that terminates the task if it exceeds a specific time limit (e.g., 1800s).
- **Concurrency:** Extraction concurrency is configurable to balance speed vs. rate limits.

---

## 3. Configuration (Settings)

The behavior of Deep Research is tuned via `data/settings.json`:
- `research_model`: The LLM used for planning and synthesis.
- `research_search_provider`: The specific provider used for the research phase.
- `research_max_tokens`: Token limit for the final synthesis.
- `research_run_timeout_seconds`: Total time allowed for a research run.
- `research_extraction_concurrency`: How many pages are processed in parallel.

## 4. AI Agent Integration
The agent can trigger Deep Research by invoking the research tool. The agent provides the initial query and can later retrieve the completed report and sources to answer user questions with high factual density.