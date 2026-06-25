"""Guards that async tests actually run in CI.

Without `asyncio_mode = "auto"` in pyproject, an `async def test_*`
is collected but not awaited (pytest-asyncio default is "strict"),
so its body never executes and false-passes. This test fails loudly
unless auto mode is configured.
"""

import asyncio


async def test_event_loop_is_running():
    # Only true if pytest-asyncio actually drove this coroutine.
    loop = asyncio.get_running_loop()
    assert loop.is_running()
