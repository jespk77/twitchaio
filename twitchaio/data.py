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

import json
import shutil

class DataContainer:
    def __init__(self, filename, delimiter="."):
        self._filename = filename
        self._delimiter = delimiter
        self._data = {}
        self._load()

    def _load(self):
        try:
            with open(self._filename, "r") as file:
                self._data = json.load(file)
        except FileNotFoundError: pass

    def _save(self):
        backup_file = f"{self._filename}.bkp"
        shutil.copy(self._filename, backup_file)
        with open(self._filename, "w") as file:
            try: json.dump(self._data, file, indent=5)
            except: shutil.copy(backup_file, self._filename)
    save = _save

    def clear(self):
        self._data.clear()
        self._save()

    def get(self, key, default=None):
        key = key.split(self._delimiter)
        data = self._data
        while len(key) > 1:
            data = data.get(key.pop(0))
            if data is None: return default
        return data.get(key[0], default)

    def get_or_create(self, item, create_value=None):
        value = self._data.get(item)
        if value is None:
            if create_value is None: create_value = {}
            self._data[item] = value = create_value
        return value

    def __contains__(self, item):
        item = item.split(self._delimiter)
        data = self._data
        while len(item) > 1:
            key = item.pop(0)
            if key not in data: return False
            data = data[key]
        return item[0] in data

    def __getitem__(self, item):
        item = item.split(self._delimiter)
        data = self._data
        while len(item) > 1: data = data[item.pop(0)]
        return data[item[0]]

    def __setitem__(self, key, value):
        key = key.split(self._delimiter)
        data = self._data
        while len(key) > 1:
            name = key.pop(0)
            try: data = data[name]
            except KeyError: data[name] = data = {}
        data[key[0]] = value
        self._save()

    def __delitem__(self, key):
        key = key.split(self._delimiter)
        data = self._data
        while len(key) > 1: data = data[key.pop(0)]
        del data[key[0]]
        self._save()

    def __len__(self): return len(self._data)
    def __str__(self): return str(self._data)

    def reload(self):
        self._data.clear()
        self._load()