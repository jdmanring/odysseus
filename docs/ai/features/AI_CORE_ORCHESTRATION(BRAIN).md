# AI FEATURE BRAIN (MEMORY SYSTEM)

The "Brain" is the central knowledge and memory system of Odysseus. It allows the agent to persist information across sessions, retrieve relevant facts based on context, and manage a long-term knowledge base.

## 1. Architecture Overview

The Brain uses a hybrid storage approach to combine metadata flexibility with semantic retrieval.

- **Metadata Store:** JSON-based storage (via `MemoryManager`) for full-text entries, categories, timestamps, and ownership.
- **Vector Store:** ChromaDB (via `MemoryVector`) for high-dimensional embeddings, enabling semantic search.
- **Embedding Engine:** Configurable via `src/embeddings.py` (supports local providers like Ollama/llama.cpp or cloud providers).

---

## 2. Core Capabilities

### Semantic Retrieval (Search)
When the agent or user searches the Brain, it doesn't just match keywords. It performs a **Vector Search**:
1. The query is converted into an embedding vector.
2. The vector store calculates the cosine similarity between the query and all stored memories.
3. Memories exceeding a specific similarity threshold (default `0.05`) are returned as "relevant."

### Memory Extraction
The system can automatically identify "memorable" information from conversations.
- **Session Extraction:** Analyzes the chat history of a specific session using an LLM to identify factual statements, contacts, or preferences.
- **Document Import:** Processes uploaded files (PDF, TXT, MD, JSON). The text is passed to an LLM with a specialized extraction prompt to isolate "personal, memorable information" into structured facts.

### Memory Audit (The "Tidy" Process)
To prevent "memory bloat" and contradiction, the system includes an Audit feature:
- **Deduplication:** Identifies and merges redundant facts.
- **Consolidation:** Uses an LLM to combine related small facts into a single, more comprehensive entry.

---

## 3. API Map & Functional Flow

### `/api/memory/add`
- **Action:** Creates a new memory entry.
- **Flow:** 
    1. Checks for exact duplicates.
    2. Saves metadata to the JSON store.
    3. Syncs the text to the Vector Index for future retrieval.

### `/api/memory/search`
- **Action:** Retrieves relevant memories.
- **Filters:** Can filter by `session_id` or `category`.
- **Result:** Returns a list of semantically similar memories.

### `/api/memory/extract`
- **Action:** Generates memory suggestions from a session.
- **Flow:** `Session History` $\rightarrow$ `LLM Extraction Prompt` $\rightarrow$ `Suggested JSON list`.

### `/api/memory/audit`
- **Action:** Cleans and consolidates the memory base.
- **Flow:** `All Memories` $\rightarrow$ `LLM Consolidation Logic` $\rightarrow$ `Updated Store`.

### `/api/memory/import`
- **Action:** Extracts facts from a file.
- **Flow:** `File Upload` $\rightarrow$ `Text Extraction` $\rightarrow$ `LLM Fact Isolation` $\rightarrow$ `Suggested JSON list`.

---

## 4. Data Schema

Every memory entry contains:
- `id`: Unique identifier.
- `text`: The actual factual statement.
- `category`: (e.g., `identity`, `preference`, `fact`, `contact`, `project`, `goal`).
- `source`: Where the memory came from (e.g., `user`, `session`, `import`).
- `timestamp`: Epoch time of creation.
- `owner`: The user ID who owns the memory (strict isolation).
- `session_id`: (Optional) Link to the session where the memory was generated.

## 5. AI Agent Interaction
The agent interacts with the Brain via tools (e.g., `save_memory`, `search_memory`). This allows the agent to "learn" about the user in real-time and retrieve that knowledge in subsequent turns to provide personalized responses.