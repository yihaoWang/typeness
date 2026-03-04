# Typeness

Local voice input tool that converts speech to structured written text using Whisper and Qwen3. Works as a global voice input method — press a hotkey or click the menu bar icon in any application, speak, and the processed text is automatically pasted at the cursor position.

## Prerequisites

- **macOS** (Apple Silicon with MPS) or **Windows** (NVIDIA GPU with CUDA)
- Python 3.12
- [uv](https://docs.astral.sh/uv/) package manager
- **macOS only**: grant Accessibility permission to your terminal (System Settings → Privacy & Security → Accessibility)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd typeness

# Create virtual environment and install dependencies
uv sync
```

PyTorch is installed from standard PyPI, which supports CUDA, MPS (Apple Silicon), and CPU automatically. For CUDA-specific optimization, see the commented `[tool.uv.sources]` section in `pyproject.toml`.

## Usage

```bash
uv run typeness
```

To enable debug mode (saves each recording as WAV + JSON to `debug/`):

```bash
uv run typeness --debug
```

On first run, Whisper (`openai/whisper-large-v3-turbo`) and Qwen3 (`Qwen/Qwen3-1.7B`) models will be downloaded from HuggingFace automatically.

### How it works

1. Launch the program — a menu bar icon (🎙) appears and the terminal shows status
2. Press **Shift+Control+A** or click the menu bar icon to start recording (works in any application)
3. Speak into your microphone (in Traditional Chinese)
4. Press **Shift+Control+A** again or click the menu bar icon to stop recording
5. The processed text is automatically pasted into the focused window
6. During transcription/processing, press the hotkey or click "取消" in the menu to cancel
7. The terminal displays:
   - **Whisper raw**: original speech-to-text result
   - **LLM processed**: cleaned and formatted text (punctuation added, lists formatted)
   - **Timing stats**: recording duration, Whisper latency, LLM latency, total latency
8. Click "退出" in the menu bar or press **Ctrl+C** to exit

### Auto-start at login (macOS)

```bash
uv run typeness --install-login-item      # install as login item
uv run typeness --uninstall-login-item    # remove login item
```

Logs are written to `~/Library/Logs/typeness.log`.

## Regression Testing

Claude Code skills for maintaining transcription quality:

- **`/fix-transcription`** — Create a test case from a debug recording, diagnose the issue, and fix it
- **`/run-regression`** — Replay all test cases and judge results (LLM-as-Judge)

Test cases live in `tests/fixtures/` (WAV audio + `cases.json`). The replay engine can also be run directly:

```bash
uv run python -m typeness.replay --stage llm      # LLM post-processing only (fastest)
uv run python -m typeness.replay --stage whisper   # Whisper only
uv run python -m typeness.replay --stage full      # full pipeline
uv run python -m typeness.replay --help            # all options
```

## Architecture

Modular design with unified PyTorch + transformers inference engine. Source code lives in `src/typeness/`:

- `main.py` — worker thread event loop + menu bar app on main thread
- `audio.py` — microphone recording (sounddevice), auto-resample to 16kHz via scipy
- `transcribe.py` — Whisper speech-to-text and CJK text normalization
- `postprocess.py` — Qwen3 LLM text cleanup (punctuation, list formatting), cancellable generation
- `hotkey.py` — global keyboard listener (Shift+Control+A toggle via pynput), macOS CGEventTap recovery
- `menubar.py` — macOS menu bar UI (rumps), state display and controls
- `clipboard.py` — clipboard write and auto-paste (pyperclip + pynput Controller)
- `login_item.py` — macOS LaunchAgent management for auto-start

### Models

- **Speech recognition**: Whisper large-v3-turbo (FP16 on CUDA, FP32 on MPS)
- **Text post-processing**: Qwen3-1.7B (FP16)
- **Audio capture**: sounddevice (16kHz mono float32; auto-resamples if device native rate differs)
- **Device auto-detection**: CUDA → MPS → CPU
