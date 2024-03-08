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

import datetime
import json, logging, time

from . import chat as twitch_chat, tags, data

log = logging.getLogger("twitch.commands")
log.setLevel(logging.DEBUG)
class Command:
    def __init__(self, name, callback, cooldown=7, user_level=0):
        self.name = name
        self.callback = callback
        self.cooldown = cooldown
        self.user_level = user_level
        self._last_use_time = 0

    def has_permission(self, user_level):
        return user_level >= self.user_level

    def is_cooldown(self):
        current = time.time()
        if (current - self._last_use_time) < self.cooldown: return True
        self._last_use_time = current
        return False

    async def execute(self, command, message):
        if message is None or (self.has_permission(message.meta.user_level) and not self.is_cooldown()):
            if self.callback.__code__.co_argcount > 2: return await self.callback(command, message)
            else: return await self.callback(message)

class TextCommand(Command):
    def __init__(self, name, text, cooldown=7, user_level=0):
        Command.__init__(self, name, self._reply_message, cooldown, user_level)
        self.text = text

    async def execute(self, command, message):
        if message is None: return await self._reply_message(None) if not self.is_cooldown() else None
        else: return await Command.execute(self, command, message)

    async def _reply_message(self, _):
        return self.text

class CounterCommand(Command):
    def __init__(self, name, text, container, cooldown=30, user_level=0):
        Command.__init__(self, name, self.reply_message, cooldown, user_level)
        self.text = text
        self._data = container
        if self.name not in self._data: self._data[name] = {"today": 0, "total": 0}

    @staticmethod
    def _current_date():
        now = datetime.datetime.now()
        return f"{now.year}-{now.month}-{now.day}"

    def _check_date(self):
        current = self._current_date()
        try:
            if current != self._data[f"{self.name}.last_used"]: self._data[f"{self.name}.today"] = 0
        except KeyError: pass
        self._data[f"{self.name}.last_used"] = current

    async def reply_message(self, command, message):
        self._check_date()

        if command.startswith("+"):
            count = 1
            if message.meta.moderator:
                try: count = int(message.content[0])
                except (IndexError, ValueError): pass

            self._data[f"{self.name}.today"] += count
            self._data[f"{self.name}.total"] += count
            return f"(+ {abs(count)}) {self.text.format_map(self._data[self.name])}"
        if command.startswith("!"):
            if message.meta.user_level >= tags.UserLevel.Mod:
                command = message.content[0]
                if command == "today":
                    try: self._data[f"{self.name}.today"] = int(message.content[1])
                    except (IndexError, ValueError): return f"{message.meta.display_name} command syntax !{self.name} today [count]"
                if command == "total":
                    try: self._data[f"{self.name}.total"] = int(message.content[1])
                    except (IndexError, ValueError): return f"{message.meta.display_name} command syntax !{self.name} total [count]"
            return self.text.format_map(self._data[self.name])

class ChatCommands:
    def __init__(self, chat : twitch_chat.Chat, command_file: str=None, command_data=None):
        self._chat = chat
        self._chat.add_connected_callback(self._load)
        self._chat.add_message_callback(self._on_message, tags.PRIVMSG.type)

        self._command_file = command_file
        if command_data is None: self._data = None
        elif isinstance(command_data, data.DataContainer): self._data = command_data
        elif isinstance(command_data, str): self._data = data.DataContainer(command_data)
        else: raise TypeError("'command_data' must be a DataContainer or a string")
        self._commands = {}
        self._command_data = {"commands": {}, "alias": {}, "alias_content": {}}

    @property
    def data(self): return self._data

    async def _load(self):
        try:
            if self._command_file is not None:
                with open(self._command_file, "r") as file:
                    self._command_data = json.load(file)
                for command, text in self._command_data["commands"].items():
                    self._commands[command] = TextCommand(command, text)
                for alias, command in self._command_data["alias"].items():
                    self.add_alias(alias, command)
                return
        except FileNotFoundError: pass

    def _save(self):
        if self._command_file is not None:
            with open(self._command_file, "w") as file:
                json.dump(self._command_data, file, indent=5)

    async def _on_message(self, message):
        command = self._commands.get(message.content[0].lower())
        if command is not None:
            name = message.content.pop(0).lower()
            log.debug(f"Executing command: {command.name}")
            content = self._command_data["alias_content"].get(name)
            if content: message.content[0:0] = content

            if result := await command.execute(name, message):
                log.debug(f"Returning text as as chat message: '{result}'")
                await self._chat.send_message(result, message.channel)

    def add_command(self, command : Command, *names):
        if not names: names = [command.name]
        for name in names: self._commands[name.lower()] = command
        return self

    def add_text_command(self, command, text, user_level=0, cooldown=7):
        try:
            command = command.lower()
            cmd = self._commands[command]
            cmd.text, cmd.user_level, cmd.cooldown = text, user_level, cooldown
        except KeyError:
            self._commands[command] = TextCommand(command, text, cooldown, user_level)

        self._command_data["commands"][command] = text
        self._save()
        return self

    def add_alias(self, alias, command):
        if isinstance(command, list):
            name = command[0]
            command = command[1:]
        elif isinstance(command, str):
            name = command
            command = []
        else: raise TypeError("'command' must be list or str")

        alias, name = alias.lower(), name.lower()
        self._commands[alias] = self._commands[name]
        self._command_data["alias"][alias] = name
        if command: self._command_data["alias_content"][alias] = [c.lower() for c in command]
        self._save()
        return self

    def remove_alias(self, alias, save=True):
        alias = alias.lower()
        del self._commands[alias]
        del self._command_data["alias"][alias]
        try: del self._command_data["alias_content"]
        except KeyError: pass
        if save: self._save()
        return self

    def Command(self, command, user_level=0, cooldown=7):
        def wrapper(cb):
            self.add_command(Command(command, cb, user_level=user_level, cooldown=cooldown))
        return wrapper

    def remove_command(self, command):
        command = command.lower()
        if (actual_command := self._command_data["alias"].get(command)) is not None: return self.remove_command(actual_command)

        del self._commands[command]
        try: del self._command_data["commands"][command]
        except KeyError: return

        for alias, alias_command in self._command_data["alias"].copy().items():
            if command == alias_command: self.remove_alias(alias, save=False)
        self._save()
        return self

    def __contains__(self, item): return item in self._commands
    def __getitem__(self, item): return self._commands[item]
    def __len__(self): return len(self._commands)