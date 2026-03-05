"""Whisper speech recognition module for Typeness.

Loads the Whisper model and provides transcription with CJK text normalization.
"""

import re
import time

import numpy as np
import mlx_whisper

WHISPER_MODEL_ID = "mlx-community/whisper-large-v3-turbo"
WHISPER_INITIAL_PROMPT = "以下是繁體中文夾雜英文的語音內容，英文請保留原文不要翻譯。"

# Half-width -> full-width punctuation mapping for CJK text
_PUNCTUATION_MAP = str.maketrans({
    ",": "，",
    ":": "：",
    ";": "；",
    "!": "！",
    "?": "？",
    "(": "（",
    ")": "）",
})


def _normalize_punctuation(text: str) -> str:
    """Replace half-width punctuation with full-width equivalents for CJK text."""
    return text.translate(_PUNCTUATION_MAP)


def _add_cjk_spacing(text: str) -> str:
    """Insert a space between CJK and Latin/digit characters where missing."""
    # CJK before Latin/digit: 中A -> 中 A
    text = re.sub(
        r"([\u4e00-\u9fff\u3400-\u4dbf])([A-Za-z0-9])", r"\1 \2", text
    )
    # Latin/digit before CJK: A中 -> A 中 (but not punctuation before CJK)
    text = re.sub(
        r"([A-Za-z0-9])([\u4e00-\u9fff\u3400-\u4dbf])", r"\1 \2", text
    )
    return text


def load_whisper():
    """Load Whisper model and return the model path string."""
    print(f"Loading Whisper model ({WHISPER_MODEL_ID})...")
    # Trigger model download/cache by running a dummy transcribe
    mlx_whisper.transcribe(
        np.zeros(16000, dtype=np.float32),
        path_or_hf_repo=WHISPER_MODEL_ID,
    )
    print("Whisper model loaded.")
    return WHISPER_MODEL_ID


def transcribe(model_path: str, audio: np.ndarray) -> str:
    """Transcribe audio using mlx-whisper."""
    start = time.time()

    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model_path,
        initial_prompt=WHISPER_INITIAL_PROMPT,
        temperature=0.0,
    )

    elapsed = time.time() - start
    text = _normalize_punctuation(result["text"])
    print(f"Whisper result ({elapsed:.2f}s): {text}")
    return text
