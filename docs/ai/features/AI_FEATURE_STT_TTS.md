# AI FEATURE: STT & TTS
The Sensory suite provides the system with the ability to hear (Speech-to-Text) and speak (Text-to-Speech), bridging the gap between text-based LLMs and voice interaction.

## 1. Text-to-Speech (TTS)
The TTS system acts as a routing gateway to multiple voice engines:
- **Edge-TTS Engine:** A high-performance, cloud-based engine (utilizing Microsoft Edge's neural voices) that provides natural-sounding speech without requiring complex API keys.
- **Custom API Integration:** Supports connection to other TTS providers via REST endpoints.
- **Audio Caching:** To reduce latency and API costs, generated audio is cached based on a hash of the `text + voice_id`. If the same phrase is requested again, the system serves the cached `.mp3`/`.wav` file.

## 2. Speech-to-Text (STT)
The STT system converts spoken audio into high-accuracy text:
- **Whisper Integration:** Utilizes OpenAI's Whisper (typically via `faster-whisper` for local efficiency) to perform transcription.
- **Auto-Language Detection:** The system automatically detects the spoken language at the start of the audio stream before initiating the transcription process.
- **Modalities:** Supports both **File-based** (uploading a recording) and **Stream-based** (real-time voice input) transcription.

## 3. AI Implementation Notes
When interacting via voice, the AI should:
1.  **Keep TTS Concise:** Avoid extremely long paragraphs when using TTS, as it can be taxing for the listener. Use bullet points or short sentences.
2.  **Verify STT Accuracy:** If the transcription contains obvious "hallucinations" or phonetic errors (e.g., "Odysseus" transcribed as "Odisious"), use context to correct the term before processing.
3.  **Match Voice to Tone:** Suggest different voice IDs based on the context (e.g., a professional voice for reports, a friendly voice for reminders).