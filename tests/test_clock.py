import asyncio

import pytest

from relay.clock import FakeClock, RealClock


@pytest.mark.asyncio
async def test_fake_sleep_advances_virtual_time():
    c = FakeClock(start=100.0)
    assert c.now() == 100.0
    await c.sleep(2.5)
    assert c.now() == pytest.approx(102.5)


@pytest.mark.asyncio
async def test_fake_sleep_negative_is_noop():
    c = FakeClock()
    await c.sleep(-5)
    assert c.now() == 0.0


@pytest.mark.asyncio
async def test_fake_clock_never_reads_wall_time():
    c = FakeClock(start=0.0)
    await asyncio.sleep(0.02)
    assert c.now() == 0.0


@pytest.mark.asyncio
async def test_real_clock_is_monotonic_and_sleeps():
    c = RealClock()
    t0 = c.now()
    await c.sleep(0.01)
    t1 = c.now()
    assert t1 > t0
    assert t1 - t0 >= 0.005


@pytest.mark.asyncio
async def test_cancelled_sleep_propagates():
    """Rule 8: CancelledError must never be swallowed by the clock."""
    c = FakeClock()
    started = asyncio.Event()

    async def sleeper():
        started.set()
        await c.sleep(100)

    task = asyncio.create_task(sleeper())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_fake_clock_advance_helper():
    c = FakeClock(start=1.0)
    c.advance(0.5)
    assert c.now() == pytest.approx(1.5)
