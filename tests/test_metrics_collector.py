import asyncio

from observability.metrics import collect_once


def test_collect_once_runs():
    # Run collect_once coroutine to ensure it doesn't raise
    loop = asyncio.new_event_loop()
    loop.run_until_complete(collect_once())
    loop.close()
