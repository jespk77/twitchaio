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

import logging
import asyncio, websockets
from typing import Callable

import twitchaio
from . import utils

from collections import namedtuple

ChatMessage = namedtuple("ChatMessage", ["channel", "meta", "content"])
MessageCallback = namedtuple("MessageCallback", ["callback", "tag_filter"])

log = logging.getLogger("twitchaio.chat")

class Chat:
    """
        Manages the connection to twitch chat:
        * Receives incoming messages (+ monitors PING messages)
        * Sends outgoing messages (+ monitors rate limits)
        * Automatically reconnects on connection drop
    """
    chat_url = "wss://irc-ws.chat.twitch.tv:443"

    def __init__(self, authentication: twitchaio.OAuth, *channels: str):
        self._send_message_queue : asyncio.Queue = None
        self._receive_message_queue : asyncio.Queue = None
        self._channels = channels
        self._socket = None
        self._authentication = authentication
        self._message_callbacks = set()
        self._connected_callbacks = set()
        self._task = asyncio.create_task(self._main(), name="Chat")

    async def _connect(self):
        if self._socket is not None:
            print("(re)connect")
            await self._authentication.load()
            code = await self._authentication.get_code()
            if code is None: raise PermissionError("No authorization code")

            await self._send(f"PASS oauth:{code}")
            await self._send(f"NICK {self._authentication.user_name}")
            await self._send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            log.info(f"Joining {self._channels}...")
            await self._send(f"JOIN #{',#'.join(self._channels)}")
        else: raise ValueError("No socket available")

    async def _disconnect(self):
        if self._socket is not None:
            log.info("Disconnecting from chat...")
            await self._send(f"PART #{self._authentication.user_name},#{','.join(self._channels)}")
            await self._send("QUIT")

    async def _send(self, message):
        await self._send_message_queue.put(message)

    async def _send_handler(self):
        while True:
            message = await self._send_message_queue.get()
            await self._socket.send(message)

    async def _receive_handler(self):
        try:
            async for data in self._socket:
                for message in data.rstrip("\r\n\U000e0000").split("\r\n"):
                    message = utils.SafeList(message.split(" ", maxsplit=4))
                    if message[0] == "PING":
                        await self._send(f"PONG {message[1]}")
                        continue
                    elif message[1] == "NOTICE":
                        log.warning(f"[Notice] {' '.join(message[2:])}")
                        continue

                    # parse message and add to received queue for further processing
                    channel = message[3]
                    meta = twitchaio.tags.parse_tags(message[2], message[1][1:], message[0])
                    content = message[4][1:]
                    await self._receive_message_queue.put(ChatMessage(channel, meta, utils.SafeList(content.split(" "))))
        except websockets.ConnectionClosedError: print("chat connection closed")
        except Exception as e: log.exception(e)

    async def _message_handler(self):
        while True:
            message = await self._receive_message_queue.get()
            for callback, tag_filter in self._message_callbacks:
                try:
                    if tag_filter is None or message.meta.type == tag_filter:
                        await callback(message)
                except asyncio.CancelledError: return
                except Exception as e: log.exception(e)
            self._receive_message_queue.task_done()

    def add_message_callback(self, func: Callable, tag_filter: str=None):
        """
            Add a callback for incoming messages, allows filtering on a specific tag (see tags.<tag_name>.type)
            func: must be a function accepting one parameter of type ChatMessage
            tag_filter: the message tag the callback should be called on, if None it is called for all tags
        """
        self._message_callbacks.add(MessageCallback(func, tag_filter))

    def remove_message_callback(self, func: Callable, tag_filter: str=None):
        """
            Remove a previously added callback for incoming messages.
            The tag filter must match the one added for it to be removed
            Raises KeyError when a callback was not registered
        """
        self._message_callbacks.remove(MessageCallback(func, tag_filter))

    def Message(self, tag_filter=None):
        def _cb(cb):
            self.add_message_callback(cb, tag_filter)
        return _cb

    def add_connected_callback(self, func: Callable):
        self._connected_callbacks.add(func)

    def remove_connected_callback(self, func: Callable):
        self._connected_callbacks.remove(func)

    def Connection(self):
        def _cb(cb): self.add_connected_callback(cb)
        return _cb

    async def send_message(self, message: str, channel: str):
        """ Send a chat message to a channel, must have been previously joined (so one of the channels passed in the constructor) """
        if not channel.startswith('#'): channel = f"#{channel}"
        try: print(channel, "->", message)
        except UnicodeError as e: logging.exception(e)
        await self._send(f"PRIVMSG {channel} :{message}")
        return True

    async def _main(self):
        # initialize the queues here instead of in __init__ so that they're attached to the right loop
        self._send_message_queue = asyncio.Queue()
        self._receive_message_queue = asyncio.Queue()

        pending = []
        async for websocket in websockets.connect(self.chat_url, ssl=True):
            try:
                self._socket = websocket
                await self._connect()
                for cb in self._connected_callbacks:
                    try: await cb()
                    except Exception as e: log.exception(e)

                sender = asyncio.create_task(self._send_handler())
                receiver = asyncio.create_task(self._receive_handler())
                processor = asyncio.create_task(self._message_handler())
                completed, pending = await asyncio.wait([sender, receiver, processor], return_when=asyncio.FIRST_COMPLETED)

            # console received interrupt
            except asyncio.CancelledError:
                log.info("Disconnecting chat...")
                await self._disconnect()
                break

            except PermissionError:
                print("Not authorized")
                break

            except Exception as e:
                log.exception(e)

            finally:
                for task in pending: task.cancel()
                await websocket.close()
                self._socket = None