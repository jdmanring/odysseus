# AI FEATURE COMPARE

The "Compare" feature allows users to send a single prompt to multiple AI models simultaneously, viewing their responses side-by-side. This is primarily used for model evaluation, blind testing, and finding the best model for a specific task.

## 1. Core Workflow

The Compare feature is a UI-driven mode that orchestrates multiple concurrent LLM requests.

1. **Model Selection:** The user selects two or more models from the available provider list.
2. **Prompting:** A single input is provided.
3. **Parallel Execution:** Odysseus sends the prompt to all selected model endpoints in parallel.
4. **Side-by-Side Rendering:** Responses are streamed into separate panes in the UI for immediate comparison.

---

## 2. Key Modes & Features

### Blind Testing (Bias Reduction)
To prevent brand bias, Odysseus supports a **Blind Compare** mode:
- **Redaction:** Model names are hidden from the user during the generation process.
- **Labeling:** Models are labeled generically (e.g., "Model A", "Model B").
- **Reveal:** Model identities are only revealed after the user has voted or decided on a preference.

### Shared Context (Pre-Search)
To ensure a fair comparison when using RAG (Retrieval-Augmented Generation):
- **Shared Search:** If the prompt triggers a web search, the system performs the search **once** and shares the exact same set of retrieved documents across all model panes.
- **Consistency:** This ensures that differences in output are due to the model's reasoning, not because one model found better search results than another.

### Tool Constraints
In Compare mode, the behavior of agent tools is modified:
- **Tool Disabling:** Certain complex agent tools are disabled to keep the comparison focused on the raw generation capabilities of the models.
- **Single-Shot Nature:** Compare panes are typically short-lived, single-turn interactions rather than long-term sessions.

---

## 3. Technical Implementation

### Frontend Orchestration
- **State Management:** The `compareModule` in `static/app.js` manages the active panes, selected models, and the submission loop.
- **UI Layout:** Reuses the chat container but splits it into a multi-column layout.

### Backend Handling
- **Stream Multiplexing:** The backend (`routes/chat_routes.py`) handles the streaming responses for each model independently.
- **Session Management:** Compare sessions are treated as lightweight, transient objects compared to full chat sessions.

---

## 4. Use Cases for AI Agents
An AI agent can use the Compare feature to:
- **Quality Benchmarking:** Test a prompt against multiple models to determine which one follows instructions most accurately.
- **Ensembling:** Use the responses from multiple models to synthesize a "consensus" answer.
- **Model Selection:** Dynamically choose the best model for a specific sub-task based on previous compare results.