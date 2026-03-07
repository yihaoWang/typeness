"""Typeness main entry point.

Event-driven loop: hotkey -> record -> transcribe -> process -> paste.
"""

import queue
import threading
import time
import traceback

from typeness.audio import MIN_RECORDING_SECONDS, SAMPLE_RATE, record_audio_start, record_audio_stop, stop_stream
from typeness.clipboard import paste_text
from typeness.debug import DEBUG_DIR, save_capture
from typeness.hotkey import EVENT_CANCEL, EVENT_START_RECORDING, EVENT_STOP_RECORDING, HotkeyListener
from typeness.menubar import TypenessMenuBar
from typeness.postprocess import load_llm, process_text
from typeness.transcribe import load_whisper, transcribe


def _event_loop(
    model_path,
    llm_model,
    tokenizer,
    event_queue: queue.Queue,
    listener: HotkeyListener,
    menu_app: TypenessMenuBar,
    debug: bool,
    shutdown_event: threading.Event,
    cancel_event: threading.Event,
) -> None:
    """Worker thread: processes hotkey events and runs the transcribe/LLM pipeline."""
    while not shutdown_event.is_set():
        try:
            event = event_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if event == EVENT_START_RECORDING:
                menu_app.set_state("recording")
                # Run record_audio_start() in a thread — sd.InputStream.start() can
                # block indefinitely if CoreAudio is interrupted (e.g. after Space switch).
                _start_error: list[Exception | None] = [None]
                _start_done = threading.Event()

                def _do_start() -> None:
                    try:
                        record_audio_start()
                    except Exception as exc:
                        _start_error[0] = exc
                    finally:
                        _start_done.set()

                threading.Thread(target=_do_start, daemon=True).start()
                if not _start_done.wait(timeout=5.0):
                    print("[audio] record_audio_start timed out — resetting state")
                    stop_stream()
                    listener._recording = False
                    menu_app.set_state("idle")
                    continue
                if _start_error[0] is not None:
                    raise _start_error[0]

            elif event == EVENT_CANCEL:
                # Handled directly via cancel_event.set() from hotkey/menu;
                # this branch is a no-op but drains any queued cancel tokens.
                pass

            elif event == EVENT_STOP_RECORDING:
                audio = record_audio_stop()
                cancel_event.clear()
                listener.busy = True
                menu_app.set_state("transcribing")

                try:
                    rec_duration = len(audio) / SAMPLE_RATE
                    if rec_duration < MIN_RECORDING_SECONDS:
                        print("Recording too short, skipping.\n")
                        menu_app.set_state("idle")
                        continue

                    # Transcribe
                    print("Transcribing...")
                    t0 = time.time()
                    whisper_text = transcribe(model_path, audio)
                    whisper_elapsed = time.time() - t0

                    if cancel_event.is_set():
                        print("已取消。\n")
                        menu_app.set_state("idle")
                        continue

                    if not whisper_text.strip():
                        print("No speech detected, skipping.\n")
                        menu_app.set_state("idle")
                        continue

                    # LLM post-processing
                    menu_app.set_state("processing")
                    print("Running LLM post-processing...")
                    t1 = time.time()
                    processed_text = process_text(llm_model, tokenizer, whisper_text, cancel_event)
                    llm_elapsed = time.time() - t1

                    if cancel_event.is_set():
                        print("已取消。\n")
                        menu_app.set_state("idle")
                        continue

                    total_elapsed = whisper_elapsed + llm_elapsed

                    # Auto-paste to focused window
                    paste_text(processed_text)
                    menu_app.set_state("done")  # reverts to idle automatically after 1.5s

                    # Debug capture (after paste so it doesn't affect perceived latency)
                    if debug or menu_app._app_settings.debug_mode:
                        save_capture(
                            audio, whisper_text, processed_text,
                            rec_duration, whisper_elapsed, llm_elapsed,
                        )

                    # Display results
                    print("\n" + "=" * 50)
                    print("[Whisper raw]")
                    print(whisper_text)
                    print("-" * 50)
                    print("[LLM processed]")
                    print(processed_text)
                    print("-" * 50)
                    print(f"Recording duration : {rec_duration:.1f}s")
                    print(f"Whisper latency    : {whisper_elapsed:.2f}s")
                    print(f"LLM latency        : {llm_elapsed:.2f}s")
                    print(f"Total latency      : {total_elapsed:.2f}s")
                    print("=" * 50 + "\n")

                except Exception:
                    listener._recording = False
                    menu_app.set_state("idle")
                    raise

                finally:
                    listener.busy = False

        except Exception:
            traceback.print_exc()
            listener.busy = False
            listener._recording = False
            menu_app.set_state("idle")


def main(*, debug: bool = False):
    """Load models, start worker thread, then run the menu bar app on the main thread."""
    print("=== Typeness ===")
    if debug:
        print(f"Debug mode ON — captures saved to {DEBUG_DIR}/")
    print("Loading models, please wait...\n")

    from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    hotkey_available = AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})

    event_queue: queue.Queue[str] = queue.Queue()
    cancel_event = threading.Event()
    listener = HotkeyListener(event_queue, cancel_event)
    shutdown_event = threading.Event()

    def cleanup():
        shutdown_event.set()
        stop_stream()
        listener.stop()
        print("\nBye!")

    menu_app = TypenessMenuBar(
        event_queue, cleanup, cancel_event,
        accessibility_granted=hotkey_available,
    )
    menu_app.set_state("loading")

    def _init_models_and_start_worker():
        print("Loading models, please wait...\n")
        model_path = load_whisper()
        llm_model, tokenizer = load_llm()

        menu_app.set_state("idle")

        from ApplicationServices import AXIsProcessTrusted
        while not AXIsProcessTrusted():
            time.sleep(1.0)
            if shutdown_event.is_set():
                return
        menu_app.clear_accessibility_error()

        listener.start()
        worker = threading.Thread(
            target=_event_loop,
            args=(model_path, llm_model, tokenizer,
                  event_queue, listener, menu_app, debug, shutdown_event, cancel_event),
            daemon=True,
        )
        worker.start()
        print("\nReady! Press Shift+Command+A or click the menu bar icon to start/stop voice input.")
        print("Press Ctrl+C or use the menu bar icon to exit.\n")

    init_thread = threading.Thread(target=_init_models_and_start_worker, daemon=True)
    init_thread.start()



    # Blocks the main thread — rumps handles the macOS event loop
    menu_app.run()
