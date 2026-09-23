"""One owned asyncio loop for cancellable planning, with bounded retirement."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, field
import logging
from threading import Event, Thread
from time import monotonic

from .adapters.base import PlanningProvider, PlanningRequest, PlanningResult
from .runtime import AgentRuntimeConfig

logger = logging.getLogger(__name__)
RETIREMENT_TIMEOUT_SECONDS = 2.0
SHUTDOWN_TIMEOUT_SECONDS = 5.0


class PlanningRetirementError(RuntimeError):
    """An obsolete request has not released the provider within its grace period."""


@dataclass(eq=False)
class PlanningHandle:
    """Thread-safe public signals, distinct from actual task retirement.

    Cancelling result alone never means provider cleanup has finished. Only the
    runtime sets finished, after the task exits or an unstarted job is removed.
    """

    request: PlanningRequest
    config: AgentRuntimeConfig
    result: Future[PlanningResult] = field(default_factory=Future)
    started: Event = field(default_factory=Event)
    waiting: Event = field(default_factory=Event)
    finished: Event = field(default_factory=Event)
    cancelled: Event = field(default_factory=Event)
    task: asyncio.Task | None = None  # The remaining fields belong to the loop.
    retirement_timer: asyncio.TimerHandle | None = None


class AsyncPlanningRuntime:
    """Own a provider, one active request and at most one pending replacement.

    Public methods are called on the game thread. Queue/task transitions and
    provider I/O run solely on the worker loop. No callback touches game objects.
    A provider that ignores cancellation blocks further work rather than causing
    replacement threads or overlapping requests to accumulate.
    """

    def __init__(self, provider: PlanningProvider):
        self.provider = provider
        self.retirement_timeout = RETIREMENT_TIMEOUT_SECONDS
        self.shutdown_timeout = SHUTDOWN_TIMEOUT_SECONDS
        self._closed = False
        self._active: PlanningHandle | None = None
        self._pending: PlanningHandle | None = None
        self._retirement_failed = False
        self._cleanup_complete = False
        # Main-thread watchdog: even a provider blocking the loop must not keep
        # the UI waiting indefinitely for a cancellation timer on that loop.
        self._retiring: PlanningHandle | None = None
        self._retirement_deadline = 0.0
        self._loop = asyncio.new_event_loop()
        self._loop.set_exception_handler(self._loop_error)
        self._thread = Thread(target=self._serve, name="wormhole-ai", daemon=True)
        self._thread.start()

    def _serve(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()
            asyncio.set_event_loop(None)

    @staticmethod
    def _loop_error(loop, context):
        # Never log task reprs, exception messages or provider payloads.
        error = context.get("exception")
        logger.warning("AI runtime cleanup diagnostic (%s).",
                       type(error).__name__ if error is not None else "unfinished task")

    def submit(self, request, config) -> PlanningHandle:
        if self._closed:
            raise RuntimeError("The planning runtime is closed.")
        handle = PlanningHandle(request, config)
        if self._retiring is not None and not self._retiring.finished.is_set():
            handle.waiting.set()
        self._loop.call_soon_threadsafe(self._enqueue, handle)
        return handle

    def cancel(self, handle: PlanningHandle) -> None:
        """Invalidate delivery immediately; schedule cancellation without waiting."""
        handle.cancelled.set()
        handle.result.cancel()
        if (handle.started.is_set() and not handle.finished.is_set()
                and (self._retiring is None or self._retiring.finished.is_set())):
            self._retiring = handle
            self._retirement_deadline = monotonic() + self.retirement_timeout
        if not self._closed:
            self._loop.call_soon_threadsafe(self._cancel, handle)

    def retirement_expired(self, handle: PlanningHandle) -> bool:
        """Game-thread deadline check, independent of the provider's event loop."""
        return (self._retiring is not None and not self._retiring.finished.is_set()
                and not handle.started.is_set() and not handle.result.done()
                and monotonic() >= self._retirement_deadline)

    def _enqueue(self, handle):
        if self._closed or handle.cancelled.is_set():
            self._discard(handle)
        elif self._retirement_failed:
            self._reject_retirement(handle)
        elif self._active is None:
            self._start(handle)
        else:
            if self._pending is not None:
                self._discard(self._pending)
            self._pending = handle
            handle.waiting.set()

    def _start(self, handle):
        self._active = handle
        handle.task = self._loop.create_task(self._plan(handle))
        handle.started.set()
        handle.task.add_done_callback(lambda task: self._finished(handle, task))

    async def _plan(self, handle):
        return await self.provider.plan_turn(handle.request, handle.config)

    @staticmethod
    def _discard(handle):
        handle.cancelled.set()
        handle.result.cancel()
        handle.finished.set()

    @staticmethod
    def _reject_retirement(handle):
        AsyncPlanningRuntime._publish(handle, error=PlanningRetirementError())
        handle.finished.set()

    @staticmethod
    def _publish(handle, *, result=None, error=None):
        try:
            if error is None:
                handle.result.set_result(result)
            else:
                handle.result.set_exception(error)
        except InvalidStateError:
            # Main-thread reset may cancel delivery between completion checks.
            if not handle.result.cancelled():
                raise

    def _cancel(self, handle):
        if self._pending is handle:
            self._pending = None
            self._discard(handle)
        elif self._active is handle and handle.retirement_timer is None:
            # Repeated resets must neither restart the deadline nor interrupt a
            # cooperative provider's cancellation cleanup a second time.
            handle.task.cancel()
            handle.retirement_timer = self._loop.call_later(
                self.retirement_timeout, self._retirement_expired, handle
            )

    def _retirement_expired(self, handle):
        if self._active is not handle or handle.task.done():
            return
        self._retirement_failed = True
        if self._pending is not None:
            self._reject_retirement(self._pending)
            self._pending = None

    def _finished(self, handle, task):
        if handle.retirement_timer is not None:
            handle.retirement_timer.cancel()
        try:
            result = task.result()
        except asyncio.CancelledError:
            handle.result.cancel()
        except Exception as error:
            self._publish(handle, error=error)
        else:
            self._publish(handle, result=result)
        handle.finished.set()
        self._active = None
        self._retirement_failed = False
        pending, self._pending = self._pending, None
        if pending is not None:
            if self._closed or pending.cancelled.is_set():
                self._discard(pending)
            else:
                self._start(pending)

    def shutdown(self) -> bool:
        """Close owned resources once, returning within the total shutdown budget.

        A non-cooperative provider is reported and cannot hold process exit open.
        Normal providers finish cancellation and client closure before loop stop.
        """
        if self._closed:
            return self._cleanup_complete
        self._closed = True
        deadline = monotonic() + self.shutdown_timeout
        self._loop.call_soon_threadsafe(
            lambda: self._loop.create_task(self._shutdown_async(deadline))
        )
        self._thread.join(max(0, deadline - monotonic()))
        if self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
        complete = self._cleanup_complete and not self._thread.is_alive()
        if not complete:
            logger.warning("AI planning cleanup did not finish within the shutdown budget.")
        return complete

    async def _shutdown_async(self, deadline):
        try:
            if self._pending is not None:
                self._discard(self._pending)
                self._pending = None
            active = self._active
            if active is not None:
                active.cancelled.set()
                active.result.cancel()
                self._cancel(active)
                await asyncio.wait({active.task}, timeout=min(
                    self.retirement_timeout, max(0, deadline - monotonic())
                ))
            close = self._loop.create_task(self.provider.aclose())
            _, pending = await asyncio.wait({close}, timeout=max(0, deadline - monotonic() - 0.05))
            if pending:
                close.cancel()
                # Give cooperative close cleanup the remainder of the budget;
                # never await an unbounded cancellation-resistant coroutine.
                await asyncio.wait({close}, timeout=max(0, deadline - monotonic() - 0.01))
            else:
                close.result()
            if active is not None and not active.finished.is_set():
                await asyncio.wait({active.task}, timeout=max(0, deadline - monotonic() - 0.05))
            self._cleanup_complete = not pending and (active is None or active.finished.is_set())
        except Exception as error:
            logger.warning("AI provider cleanup failed (%s).", type(error).__name__)
        finally:
            self._loop.stop()
