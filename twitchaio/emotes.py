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

import json, re
from collections import Counter

import twitchaio.chat

class EmoteCache:
    def __init__(self, name, emote_id=""):
        self._id = name, emote_id
        self._emote_cache = {}
        self._emote_regex = None
        self.load()

    cache_file = "{name}_emotes_{emote_id}.json"
    def load(self):
        try:
            with open(self.cache_file.format(name=self.name, emote_id=self.emote_id), "r") as file:
                self._emote_cache = json.load(file)
        except FileNotFoundError: pass
        print(f"Loaded {len(self._emote_cache)} emotes from cache '{self.name}'")

    def save(self):
        with open(self.cache_file.format(name=self.name, emote_id=self.emote_id), "w") as file:
            json.dump(self._emote_cache, file, indent=5)
        print(f"Saved {len(self._emote_cache)} emotes into cache '{self.name}'")

    @property
    def name(self): return self._id[0]
    @property
    def emote_id(self): return self._id[1]

    @property
    def emote_names(self): return self._emote_cache.keys()
    @property
    def emote_data(self): return self._emote_cache.values()

    def _generate_regex(self):
        if not self._emote_regex:
            self._emote_regex = re.compile("|".join([rf"\b{re.escape(emote)}\b" for emote in self.emote_names]))

    @property
    def regex(self):
        self._generate_regex()
        return self._emote_regex

    async def close(self): pass

    async def refresh(self):
        print("Refreshing emote cache")
        self._emote_cache.clear()
        self._emote_regex = None

    def scan_message(self, text:str):
        self._generate_regex()
        return self._emote_regex.findall(text)

class EmoteTracker:
    def __init__(self):
        self._emotes = {}
        self._emote_chain = set()
        self._emote_counter = Counter()

    def bind_emote_cache(self, cache: EmoteCache, name: str=None):
        if not name: name = cache.name
        self._emotes[name] = cache

    def remove_emote_cache(self, name: str):
        del self._emotes[name]

    async def refresh(self):
        for cache in self._emotes.values(): await cache.refresh()

    async def close(self):
        for cache in self._emotes.values(): await cache.close()

    @staticmethod
    def _scan_meta(meta, text):
        emotes = set()
        for emote in meta.emotes:
            emote_id, index = emote
            try:
                start, stop = index.split(",")[0].split("-", maxsplit=1)
                name = text[int(start):int(stop) + 1]
            except (ValueError, IndexError):
                continue
            emotes.add(f"{emote_id}-{name}")
        return emotes

    async def on_message(self, message: twitchaio.chat.ChatMessage):
        text = " ".join(message.content)
        emotes = set()
        emotes.update(self._scan_meta(message.meta, text))
        for cache in self._emotes.values():
            emotes.update(cache.scan_message(text))

        intersection, difference = self._emote_chain.intersection(emotes), self._emote_chain.difference(emotes)
        self._emote_chain = intersection.union(emotes)
        self._emote_counter.update(self._emote_chain)
        if intersection: print("emotes:", self._emote_chain)

        record = 0, None
        for emote in difference:
            value = self._emote_counter[emote]
            if value >= 3 and value > record[0]:
                record = value, emote
            del self._emote_counter[emote]
        if record[0]: return record