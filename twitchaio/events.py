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

import asyncio, json
import logging

import websockets
from collections import namedtuple

import twitchaio

Event = namedtuple("Event", ["type", "version", "condition", "callback"])

from . import API

log = logging.getLogger("twitch.events")

class KeepAliveTimer:
    def __init__(self, callback):
        self.timeout = 10
        self._cb = callback
        self._task = None

    async def _run(self):
        try:
            t = await asyncio.sleep(self.timeout)
            await self._cb()
        except asyncio.CancelledError: print("cancelled")

    def start(self):
        self._task = asyncio.ensure_future(self._run())

    def restart(self):
        if self._task is not None: self._task.cancel()
        self.start()

class EventMonitor:
    RETRY_TIME = 600
    event_url = "wss://eventsub.wss.twitch.tv/ws"

    def __init__(self, api : API):
        self._socket = None
        self._api = api
        self._data = None
        self._events = {}
        self._event_data = []
        self._registered = False
        self._keepalive = KeepAliveTimer(self._on_keep_alive_failed)
        self._task = asyncio.create_task(self._main(), name="EventMonitor")

    @property
    def session_id(self): return self._data["payload"]["session"]["id"]

    async def _on_keep_alive_failed(self):
        log.info("keepalive timeout reached, restarting connection...")
        await self._socket.close()

    async def _receive_events(self):
        try:
            async for data in self._socket:
                data = json.loads(data)
                message_type = data["metadata"]["message_type"]
                if message_type == "session_welcome":
                    log.info("Received welcome message")
                    self._data = data
                    self._keepalive.timeout = data["payload"]["session"]["keepalive_timeout_seconds"]
                    await self._try_registration()
                elif message_type == "notification":
                    await self._on_notification(data["payload"])
                elif message_type == "session_reconnect":
                    log.info("Received reconnect message")
                    self.event_url = data["payload"]["session"]["reconnect_url"]
                    await self._socket.close()
                elif message_type == "revocation":
                    log.info("Received revocation message")
                    await self._socket.close()
        except websockets.ConnectionClosedError: print("events connection closed")

    async def _register_events(self):
        for event_id, event in self._events.items():
            log.debug(f"Registering event: {event.type}")
            data = await self._api.create_eventsub_subscription(event.type, event.version, event.condition, self.session_id)
            self._event_data.append(data)
            log.debug(f"Event registration {event.type} successful: {data}")
        self._registered = True

    async def _try_registration(self):
        for _ in range(5):
            log.debug("registering events")
            try:
                await self._register_events()
                return
            except twitchaio.APIError as e:
                if e.status_code == 429:
                    log.warning("reqistration limit reached, retry later")
                else: raise
            await asyncio.sleep(self.RETRY_TIME)

    async def _on_notification(self, payload):
        try:
            event_type = payload["subscription"]["type"]
            event = self._events.get(event_type)
            if event is not None: await event.callback(payload)
            else: log.warning(f"Received unknown event: {event_type}")
        except Exception as e: log.exception(e)

    def add_event(self, event_type, event_version, event_condition, callback):
        self._events[event_type] = Event(event_type, event_version, event_condition, callback)

    def Event(self, event_type, event_version, condition):
        def wrapper(cb):
            return self.add_event(event_type, event_version, condition, cb)
        return wrapper

    async def _main(self):
        pending = []
        async for websocket in websockets.connect(self.event_url, ssl=True):
            try:
                self._socket = websocket
                await self._receive_events()

            except asyncio.CancelledError:
                log.debug("Disconnecting")
                break

            except PermissionError:
                log.error("Not authorized")
                break

            except Exception as e:
                log.exception(e)

            finally:
                for task in pending: task.cancel()
                await self._socket.close()
                self._socket = None