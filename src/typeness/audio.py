"""Audio recording module for Typeness.

Captures microphone input via sounddevice with start/stop control.
Records at the device's native sample rate and resamples to 16kHz if needed.
"""

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


def _audio_callback(indata: np.ndarray, frames: int, time_info, status) -> None:
    if status:
        print(f"  [audio warning] {status}")
    _audio_chunks.append(indata.copy())


_OPEN_RETRIES = 3
_OPEN_RETRY_DELAY = 0.5  # seconds


def _get_device_native_rate() -> int:
    device_info = sd.query_devices(kind="input")
    return int(device_info["default_samplerate"])


def record_audio_start() -> None:
    """Start recording audio from the microphone."""
    global _audio_stream, _capture_rate
    _audio_chunks.clear()

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
                    callback=_audio_callback,
                )
                _audio_stream.start()
                _capture_rate = rate
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


def stop_stream() -> None:
    """Stop and close the audio stream if active (for cleanup on shutdown)."""
    global _audio_stream
    if _audio_stream is not None:
        _audio_stream.stop()
        _audio_stream.close()
        _audio_stream = None


def record_audio_stop() -> np.ndarray:
    """Stop recording and return the audio as a 1D float32 numpy array."""
    global _audio_stream
    if _audio_stream is not None:
        _audio_stream.stop()
        _audio_stream.close()
        _audio_stream = None

    if not _audio_chunks:
        return np.array([], dtype=np.float32)

    audio = np.concatenate(_audio_chunks, axis=0).flatten()

    if _capture_rate != SAMPLE_RATE:
        from scipy.signal import resample_poly
        from math import gcd
        divisor = gcd(_capture_rate, SAMPLE_RATE)
        audio = resample_poly(audio, SAMPLE_RATE // divisor, _capture_rate // divisor).astype(np.float32)

    duration = len(audio) / SAMPLE_RATE
    print(f"Recorded {duration:.1f}s of audio")
    return audio
