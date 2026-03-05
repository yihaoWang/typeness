"""Audio recording module for Typeness.

Captures microphone input via sounddevice with start/stop control.
Records at the device's native sample rate and resamples to 16kHz if needed.

Uses a blocking-read thread instead of a Python PortAudio callback to avoid
a GIL/CoreAudio mutex deadlock on macOS when stopping the stream.
"""

import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"
MIN_RECORDING_SECONDS = 0.3

_audio_stream: sd.InputStream | None = None
_audio_chunks: list[np.ndarray] = []
_capture_rate: int = SAMPLE_RATE  # actual hardware rate used for this recording
_recording_thread: threading.Thread | None = None
_should_record: bool = False

_OPEN_RETRIES = 3
_OPEN_RETRY_DELAY = 0.5  # seconds
_READ_FRAMES = 256  # 16ms at 16kHz — short enough to exit quickly when _should_record=False


def _recording_thread_fn() -> None:
    """Read audio from the stream in a loop until stopped or stream is closed."""
    while _should_record and _audio_stream is not None:
        try:
            chunk, overflowed = _audio_stream.read(_READ_FRAMES)
            if overflowed:
                print("  [audio warning] input overflow")
            _audio_chunks.append(chunk.copy())
        except sd.PortAudioError:
            break  # stream was closed externally


def _get_device_native_rate() -> int:
    device_info = sd.query_devices(kind="input")
    return int(device_info["default_samplerate"])


def record_audio_start() -> None:
    """Start recording audio from the microphone."""
    global _audio_stream, _capture_rate, _recording_thread, _should_record
    _audio_chunks.clear()
    _should_record = True

    # Try preferred 16kHz first, fall back to device native rate
    rates_to_try = [SAMPLE_RATE]
    native_rate = _get_device_native_rate()
    if native_rate != SAMPLE_RATE:
        rates_to_try.append(native_rate)

    last_error: Exception | None = None
    for rate in rates_to_try:
        for attempt in range(_OPEN_RETRIES):
            try:
                _audio_stream = sd.InputStream(
                    samplerate=rate,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    # No Python callback — use blocking reads to avoid GIL/CoreAudio deadlock
                )
                _audio_stream.start()
                _capture_rate = rate
                _recording_thread = threading.Thread(target=_recording_thread_fn, daemon=True)
                _recording_thread.start()
                if rate != SAMPLE_RATE:
                    print(f"Recording at {rate} Hz (will resample to {SAMPLE_RATE} Hz)...")
                else:
                    print("Recording...")
                return
            except sd.PortAudioError as exc:
                last_error = exc
                print(f"  [audio] Stream open failed at {rate} Hz (attempt {attempt + 1}/{_OPEN_RETRIES}): {exc}")
                time.sleep(_OPEN_RETRY_DELAY)

    raise RuntimeError(f"Could not open audio stream after trying rates {rates_to_try}") from last_error


def _close_stream(stream: sd.InputStream, thread: threading.Thread | None) -> None:
    """Join the recording thread first (so read() is no longer active), then close the stream.

    _should_record must be set to False before calling this. With _READ_FRAMES=256 at 16kHz,
    the thread will exit within ~16ms after the flag is cleared.
    """
    if thread is not None:
        thread.join(timeout=1.0)
    try:
        stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass


def stop_stream() -> None:
    """Stop and close the audio stream if active (for cleanup on shutdown)."""
    global _audio_stream, _recording_thread, _should_record
    _should_record = False
    stream, thread = _audio_stream, _recording_thread
    _audio_stream = None
    _recording_thread = None
    if stream is not None:
        _close_stream(stream, thread)


def record_audio_stop() -> np.ndarray:
    """Stop recording and return the audio as a 1D float32 numpy array."""
    global _audio_stream, _recording_thread, _should_record
    _should_record = False
    stream, thread = _audio_stream, _recording_thread
    _audio_stream = None
    _recording_thread = None

    if stream is not None:
        _close_stream(stream, thread)

    if not _audio_chunks:
        return np.array([], dtype=np.float32)

    audio = np.concatenate(_audio_chunks, axis=0).flatten()

    if _capture_rate != SAMPLE_RATE:
        from math import gcd

        from scipy.signal import resample_poly
        divisor = gcd(_capture_rate, SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, _capture_rate // divisor).astype(np.float32)

    duration = len(audio) / SAMPLE_RATE
    print(f"Recorded {duration:.1f}s of audio")
    return audio
