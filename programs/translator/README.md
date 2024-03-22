# Twitch automatic chat translator
Python script that reads incoming Twitch chat messages and attempts to translate them in realtime. 
The script sends incoming messages automatically to Google Translate which detects the language and translates it into English

![example](example.png)

## Installation
1. Install Python 3.9 or above
2. Install dependencies: ``` pip install twitchaio googletrans==3.1.0a0 ```
3. Also follow https://github.com/jespk77/twitchaio?tab=readme-ov-file#getting-started to set up your Twitch developer application 
4. Open `translator.py` and fill in the required parameters
5. Run the script