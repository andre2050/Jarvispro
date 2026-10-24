"""
Run the Claude voice assistant (Phase 1): microphone -> Whisper -> Claude -> voice.

    python claude_voice.py

Needs anthropic_api_key in config/api_keys.json. The Gemini app (main.py) is unchanged.
"""
from core.claude_voice import run

if __name__ == "__main__":
    run()
