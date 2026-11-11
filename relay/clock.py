"""Injectable clock so gateway/limiter logic can be tested without real sleeping.

Rule 7: durations use time.monotonic() through this interface. Wall time is a label.
Every component that measures an interval takes a Clock; nothing calls
time.monotonic() / asyncio.sleep() directly outside this module.
"""
import asyncio
import time
from typing import Protocol


class Clock(Protocol):
    def now(self) -> float: ...

    async def sleep(self, s: float) -> None: ...


class RealClock:
    """Monotonic durations, real sleeps."""

    def now(self) -> float:
        return time.monotonic()

    async def sleep(self, s: float) -> None:
        await asyncio.sleep(max(0.0, s))


class FakeClock:
    """Sleep advances virtual time instantly. Single-task tests only.

    Because now() only moves when sleep() is called, a FakeClock test can never
    accidentally depend on wall-clock drift -- and any code path that forgets to
    await clock.sleep() shows up as zero elapsed time.
    """

    def __init__(self, start: float = 0.0):
        self._t = start

    def now(self) -> float:
        return self._t

    async def sleep(self, s: float) -> None:
        self._t += max(0.0, s)
        await asyncio.sleep(0)  # yield once, so a cancelled waiter still unwinds

    def advance(self, s: float) -> None:
        """Test-only: move time forward without sleeping (for simulating expiry)."""
        self._t += max(0.0, s)
