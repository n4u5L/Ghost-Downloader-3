from __future__ import annotations

import asyncio
from collections.abc import Callable
from threading import Thread
from typing import Any
from uuid import uuid4

from loguru import logger


class CoroutineRunner:

    def __init__(self, dispatcher: Callable[[Callable], None], isAlive: Callable[[Any], bool] | None = None, *, loop: asyncio.AbstractEventLoop):
        self._dispatcher = dispatcher
        self._isAlive = isAlive
        self._loop = loop
        self._thread = Thread(target=self._run, daemon=True)
        self._pending: dict[str, tuple] = {}
        self._running: dict[str, asyncio.Task] = {}

    def _run(self):
        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            if tasks:
                self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()

    def start(self):
        self._thread.start()

    def submit(
        self,
        work,
        done: Callable = None,
        failed: Callable = None,
        *args,
        owner=None,
        **kwargs,
    ) -> str:
        workId = f"wrk_{uuid4().hex}"
        if owner is not None:
            done, failed = self._guard(owner, done), self._guard(owner, failed)
            owner.destroyed.connect(lambda *_: self.cancel(workId))
        self._pending[workId] = (done, failed, args, kwargs)

        async def execute():
            result, error = None, None
            try:
                result = await work
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.opt(exception=e).error("async work failed: {}", workId)
                error = e
            finally:
                self._running.pop(workId, None)

            entry = self._pending.pop(workId, None)
            if entry is None:
                return
            done, failed, args, kwargs = entry
            if error is None:
                if done:
                    self.post(done, result, *args, **kwargs)
            elif failed:
                self.post(failed, error, *args, **kwargs)

        def schedule():
            if workId not in self._pending:
                work.close()
                return
            self._running[workId] = self._loop.create_task(execute())

        self._loop.call_soon_threadsafe(schedule)
        return workId

    def cancel(self, workId: str, finished: Callable = None) -> bool:
        self._pending.pop(workId, None)
        task = self._running.pop(workId, None)
        if task is not None:
            def scheduleCancel():
                if finished is not None:
                    task.add_done_callback(lambda _: self.post(finished))
                task.cancel()
            self._loop.call_soon_threadsafe(scheduleCancel)
            return True
        if finished is not None:
            finished()
        return False

    def post(self, callback: Callable, *args, **kwargs) -> None:
        def wrapper():
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.opt(exception=e).error("callback failed")

        self._dispatcher(wrapper)

    def _guard(self, owner, callback: Callable) -> Callable | None:
        if callback is None:
            return None
        isAlive = self._isAlive

        def guarded(*args, **kwargs):
            if isAlive is None or isAlive(owner):
                callback(*args, **kwargs)

        return guarded

    def stop(self) -> None:
        self._pending.clear()
        if self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
        self._running.clear()
