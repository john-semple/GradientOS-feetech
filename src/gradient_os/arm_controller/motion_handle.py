import threading
import time
from enum import Enum, auto
from typing import Optional, Callable


class MotionState(Enum):
    """Lifecycle states for a streaming motion handle."""
    RUNNING = auto()
    PAUSED = auto()
    CANCELLED = auto()
    DONE = auto()


class MotionHandle:
    """
    Handle returned by ``execute_timed_path()``.

    Provides lifecycle control over a streaming setpoint motion:
      - ``cancel()``    — stop immediately, path is dead (estop-equivalent)
      - ``pause()``     — stop feeding goals, hold position, path stays alive
      - ``resume()``    — resume streaming from current servo position
      - ``is_done()``   — path completed normally
      - ``wait(t)``     — block until done or timeout

    Thread-safe: the pacing thread reads state while external callers
    (UI, command API) mutate it.
    """

    def __init__(self) -> None:
        self._state = MotionState.RUNNING
        self._lock = threading.Lock()
        self._resume_event = threading.Event()
        self._resume_event.set()  # not paused initially
        self._done_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._cancel_callback: Optional[Callable] = None

    # -- internal: set by execute_timed_path implementation --
    def _set_thread(self, thread: threading.Thread) -> None:
        self._thread = thread

    def _set_cancel_callback(self, callback: Callable) -> None:
        self._cancel_callback = callback

    # -- state transitions --
    def cancel(self) -> None:
        """Stop immediately. Path is dead. The servo decelerates to the
        last written goal (~50 ms horizon). If a cancel callback is
        registered, it is invoked (e.g. to write current-position-as-goal)."""
        with self._lock:
            if self._state in (MotionState.CANCELLED, MotionState.DONE):
                return
            self._state = MotionState.CANCELLED
        # Unblock pacing thread if it was paused
        self._resume_event.set()
        if self._cancel_callback:
            try:
                self._cancel_callback()
            except Exception:
                pass

    def pause(self) -> None:
        """Stop feeding lookahead goals, hold position. Path stays alive.
        The pacing thread blocks until ``resume()`` is called."""
        with self._lock:
            if self._state != MotionState.RUNNING:
                return
            self._state = MotionState.PAUSED
        self._resume_event.clear()

    def resume(self) -> None:
        """Resume streaming from the current servo position at the nearest
        path timestamp. The pacing thread re-derives the path time from
        a sync_read and continues."""
        with self._lock:
            if self._state != MotionState.PAUSED:
                return
            self._state = MotionState.RUNNING
        self._resume_event.set()

    # -- queries --
    def is_done(self) -> bool:
        with self._lock:
            return self._state == MotionState.DONE

    def is_cancelled(self) -> bool:
        with self._lock:
            return self._state == MotionState.CANCELLED

    def is_paused(self) -> bool:
        with self._lock:
            return self._state == MotionState.PAUSED

    def is_running(self) -> bool:
        with self._lock:
            return self._state == MotionState.RUNNING

    @property
    def state(self) -> MotionState:
        with self._lock:
            return self._state

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the motion is done (completed or cancelled).
        Returns True if done, False on timeout."""
        return self._done_event.wait(timeout=timeout)

    # -- internal: called by pacing thread --
    def _mark_done(self) -> None:
        with self._lock:
            if self._state not in (MotionState.CANCELLED,):
                self._state = MotionState.DONE
        self._done_event.set()
        self._resume_event.set()

    def _wait_for_resume(self, timeout: Optional[float] = None) -> bool:
        """Block while paused. Returns True when running again, False on
        timeout or if cancelled."""
        return self._resume_event.wait(timeout=timeout)

    def _should_stop(self) -> bool:
        """Check if the pacing loop should exit (cancelled or done)."""
        with self._lock:
            return self._state in (MotionState.CANCELLED, MotionState.DONE)

    def join_thread(self, timeout: Optional[float] = None) -> None:
        """Join the pacing thread if one is registered."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)