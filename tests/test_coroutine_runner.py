from __future__ import annotations

import asyncio
from threading import Event

import pytest

from app.services.coroutine_runner import CoroutineRunner
from tests.conftest import NEW_LOOP_BY_PLATFORM


async def test_cancel_before_start_never_runs():
    loop = asyncio.get_running_loop()
    runner = CoroutineRunner(loop.call_soon, loop=loop)
    started = []
    finished = []

    async def work():
        started.append(True)

    workId = runner.submit(work())
    runner.cancel(workId, finished=lambda: finished.append(True))
    await asyncio.sleep(0.05)

    assert started == []
    assert finished == [True]


@pytest.mark.parametrize("platform", ["desktop", "android"])
@pytest.mark.parametrize("isShielded", [False, True])
def test_stop_waits_for_child_tasks_to_save_cleanup(tmp_path, platform, isShielded):
    started = Event()
    loop = NEW_LOOP_BY_PLATFORM[platform]()
    runner = CoroutineRunner(lambda callback: callback(), loop=loop)

    async def child():
        try:
            started.set()
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            (tmp_path / "cleanup.txt").write_text("saved", encoding="utf-8")

    async def work():
        children = asyncio.gather(child())
        await (asyncio.shield(children) if isShielded else children)

    runner.start()
    runner.submit(work())
    try:
        assert started.wait(5)
    finally:
        runner.stop()

    assert (tmp_path / "cleanup.txt").read_text(encoding="utf-8") == "saved"


@pytest.mark.parametrize("platform", ["desktop", "android"])
def test_stop_without_work_closes_loop(platform):
    loop = NEW_LOOP_BY_PLATFORM[platform]()
    runner = CoroutineRunner(lambda callback: callback(), loop=loop)
    runner.start()

    runner.stop()

    assert loop.is_closed()
