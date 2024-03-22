# TwitchAIO
Asynchronous Twitch interface for implementing custom chatbots

## Features
- Send/receive Twitch chat messages
- Command system for chat interaction
- Interface with the Twitch API to allow automating parts of the stream
- Websocket based events with the Twitch EventSub system

## Getting started
1. Install TwitchAIO with 
``` pip install twitchaio ```
2. Register your application on https://dev.twitch.tv/console
3. Fill in or create `client.json` in your project directory with the application data:
```
{ 
    "Client-ID": <your client id>,
    "Client-Secret": <your client secret>,
    "RedirectURI": <your redirect uri>
}
```
4. You're ready to use TwitchAIO

## Usage
Check the `examples` directory on how to use TwitchAIO

## Future updates
The following items are being worked on and will be released in the future
- Interface with emote extensions: BTTV, FFZ and SevenTV
- Interface with stream tools: StreamElements and StreamLabs

The following items are being considered and may or may not end up getting implemented
- Ability to trigger commands using regex
- Setting up a webpage that shows the list of commands