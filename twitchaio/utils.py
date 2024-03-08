"""
MIT License

Copyright (c) 2024 jespk77

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio, datetime
import logging

class SafeList(list):
    def __init__(self, iterable):
        list.__init__(self, [item for item in iterable if item])

    def __getitem__(self, item):
        try: return list.__getitem__(self, item)
        except IndexError: return ""

    def __setitem__(self, key, value):
        try: list.__setitem__(self, key, value)
        except IndexError: list.append(self, value)

    def pop(self, __index):
        try: return list.pop(self, __index)
        except IndexError: return ""

log = logging.getLogger("twitch.timer")

class Timer:
    def __init__(self, time_s : int, name=None):
        self._delay = time_s
        self._name = name
        self._cb = None
        self._task : asyncio.Task = None

    def target(self, cb):
        self._cb = cb
        return cb

    @property
    def delay(self): return self._delay
    @delay.setter
    def delay(self, delay): self._delay = delay

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._main(), name=self._name)
        return self._task

    def stop(self):
        return self._task.cancel()

    async def _main(self):
        if not self._cb: return

        log.debug(f"Starting timer \"{self._name}\"")
        while True:
            try:
                await asyncio.sleep(self._delay)
                await self._execute()
            except asyncio.CancelledError: break
            except Exception as e: log.exception(e)
        log.debug(f"Stopping timer \"{self._name}\"")

    async def _execute(self):
        await self._cb()

class ScheduleTimer(Timer):
    def __init__(self, run_time : str, name=None):
        self._run_time = [int(item) for item in run_time.split(":", maxsplit=1)]
        if len(self._run_time) < 2: self._run_time.append(0)
        Timer.__init__(self, 0, name)
        self._calculate_delay()

    def _calculate_delay(self):
        now = datetime.datetime.now()
        difference = (self._run_time[0] - now.hour) * 3600 + (self._run_time[1] - now.minute) * 60
        self._delay = difference if difference > 0 else 86400 + difference

    async def _execute(self):
        await Timer._execute(self)
        self._calculate_delay()