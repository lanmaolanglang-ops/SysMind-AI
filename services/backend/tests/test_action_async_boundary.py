import asyncio
import time

from sysmind.api.routes.actions import _run_async


def test_sync_action_boundary_does_not_block_event_loop() -> None:
    async def scenario() -> float:
        started = time.monotonic()
        action = asyncio.create_task(_run_async(lambda: time.sleep(0.2)))
        await asyncio.sleep(0.02)
        elapsed = time.monotonic() - started
        await action
        return elapsed

    assert asyncio.run(scenario()) < 0.1
