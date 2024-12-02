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

import asyncio, json, re
import googletrans, twitchaio

with open("settings.json", "r") as file:
    settings = json.load(file)
twitch_settings = settings["twitch"]
translation_settings = settings["translation"]

def create_regex_from_file(filename):
    with open(filename, "r") as file:
        return re.compile("|".join([rf"\b{re.escape(item)}" for item in file.read().split('\n')]), re.IGNORECASE)

async def main():
    auth = twitchaio.OAuth(twitch_settings["username"], twitch_settings["authentication_file"], ["chat:read", "chat:edit"])
    chat = twitchaio.Chat(auth, *twitch_settings["join_channels"])
    translator = googletrans.Translator()

    ignored_words = create_regex_from_file(settings["ignored_words_file"]) if settings["ignored_words_file"] else None
    blacklisted_words = create_regex_from_file(settings["blacklist_file"]) if settings["blacklist_file"] else None

    @chat.Message(twitchaio.tags.PRIVMSG.type)
    async def _on_message(message):
        if message.meta.emote_only or message.meta.display_name.lower() in settings["ignored_users"]: return

        text = " ".join(message.content)
        if ignored_words: text = ignored_words.sub("", text)
        if not text or text.startswith("!"): return # ignore command messages

        translation = translator.translate(text, dest=translation_settings["target_language_code"])
        if translation.src != translation.dest:
            confidence = round(translation.extra_data["confidence"] * 100)
            if confidence > translation_settings["minimal_confidence"]:
                # sometimes the "translation" is just a copy of the original message with different spaces or casing of letters
                # since these are not an actual translation they do not need to be sent out
                if text.strip(" ").lower() == translation.text.strip(" ").lower(): return
                new_text = f"[{translation.dest}/{confidence}%] {translation.text}"
                if blacklisted_words: new_text = blacklisted_words.sub("***", new_text)
                await chat.send_message(new_text, message.channel)

    done = pending = []
    try:
        done, pending = await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_EXCEPTION)
    except:
        for task in done: print("completed", task.get_name())
        for task in pending: task.cancel()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass