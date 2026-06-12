# AI FEATURE: YOUTUBE
The YouTube integration allows the system to ingest, transcribe, and synthesize information from video content, turning a visual medium into a searchable knowledge asset.

## 1. Ingestion Pipeline
The system utilizes a multi-stage pipeline to process videos:
1.  **Extraction:** Uses `yt-dlp` to extract the highest-quality audio stream from a YouTube URL without downloading the entire video file.
2.  **Transcription:** The extracted audio is passed to the **STT (Whisper)** engine to produce a raw, time-stamped text transcript.
3.  **Processing:** The raw transcript is cleaned of filler words and formatted into readable paragraphs.

## 2. AI Synthesis & Analysis
Once the transcript is generated, the AI can perform several high-level tasks:
- **Structural Summarization:** Converting a 30-minute video into a concise summary with "Key Takeaways."
- **Chapter Generation:** Identifying logical breaks in the content and creating a table of contents with timestamps.
- **Q&A over Video:** Using the transcript as a context window, the AI can answer specific questions about the video's content.

## 3. AI Implementation Notes
When processing YouTube content, the AI should:
1.  **Contextualize Timestamps:** When quoting the video, always provide the timestamp (e.g., "At 05:22, the speaker mentions...") so the user can verify the claim.
2.  **Handle Long Content:** For very long videos, the AI should process the transcript in chunks to avoid exceeding the LLM's context window.
3.  **Cross-Reference:** Suggest saving key takeaways from a video directly into a **Note** or **Codex Document** for permanent storage.