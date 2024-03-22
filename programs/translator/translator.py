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

#################################################
# Translator control parameters to tweak the bot
# Some parameters are required and some can be tweaked to your needs

# required: username of the account that will respond with translated messages
TRANSLATOR_USER = ""
# required: this file stores the credentials for the translation bot, will be created and filled on first run
TRANSLATOR_AUTH_FILE = "translator.json"
# required: the channels to join and listen for incoming messages
TRANSLATOR_CHANNELS = []

# optional: the target language code for translation, see https://py-googletrans.readthedocs.io/en/latest/#googletrans-languages for a list of supported languages and the corresponding code
TARGET_LANGUAGE_CODE = "en"
# optional: the minimum confidence % for a message to be posted to chat, used to filter out bad translations
MINIMAL_CONFIDENCE = 40
# optional: the list of users to ignore, messages from these users will not be translated, not case-sensitive
IGNORED_USERS = ["streamelements", "nightbot", "streamlabs", "moobot"]
# optional: the list of words to ignore, if a message contains any of these words they will be removed before translation
# if provided, should be a text file with one word (or combination of words) per line, not case-sensitive
# NOTE: this file is only read on startup, if the content changes the script must be reloaded
IGNORED_WORDS_FILE = ""
# optional: the list of words to blacklist, if any of these words appear in a sentence they will be replaced with ***
# if provided, should be a text file with one word (or combination of words) per line, not case-sensitive
# NOTE: this file is only read on startup, if the content changes the script must be reloaded
BLACKLIST_FILE = ""
#################################################

import asyncio, re
import googletrans, twitchaio

def create_regex_from_file(filename):
    with open(filename, "r") as file:
        return re.compile("|".join([rf"\b{re.escape(item)}" for item in file.read().split('\n')]), re.IGNORECASE)

async def main():
    auth = twitchaio.OAuth(TRANSLATOR_USER, TRANSLATOR_AUTH_FILE, ["chat:read", "chat:edit"])
    chat = twitchaio.Chat(auth, *TRANSLATOR_CHANNELS)
    translator = googletrans.Translator()

    ignored_words = create_regex_from_file(IGNORED_WORDS_FILE) if IGNORED_WORDS_FILE else None
    blacklisted_words = create_regex_from_file(BLACKLIST_FILE) if BLACKLIST_FILE else None

    @chat.Message(twitchaio.tags.PRIVMSG.type)
    async def _on_message(message):
        if message.meta.emote_only or message.meta.display_name.lower() in IGNORED_USERS: return

        text = " ".join(message.content)
        if ignored_words: text = ignored_words.sub("", text)
        if not text or text.startswith("!"): return # ignore command messages

        translation = translator.translate(text, dest=TARGET_LANGUAGE_CODE)
        if translation.src != translation.dest:
            confidence = round(translation.extra_data["confidence"] * 100)
            if confidence > MINIMAL_CONFIDENCE:
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