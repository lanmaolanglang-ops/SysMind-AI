import asyncio
import time

from sysmind.api.routes.actions import _run_async


def test_sync_action_boundary_does_not_block_event_loop() -> None:
    """The loop must keep ticking while a blocking adapter call is in flight.

    Asserting an absolute elapsed time (< 0.1s) raced with scheduler latency on a
    loaded machine. Counting loop ticks measures the same property -- the blocking
    call ran off-loop -- without depending on wall-clock timing.
    """

    async def scenario() -> int:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker = asyncio.create_task(tick())
        try:
            await _run_async(lambda: time.sleep(0.3))
        finally:
            ticker.cancel()
        return ticks

    assert asyncio.run(scenario()) >= 3
