import asyncio

USERNAME = "<username>"
CHANNEL = "<channel>" # can also be a list of channels
async def main():
    import twitchaio
    # It's fine if credentials.json doesn't exist, it'll be created on first run
    # On first boot an interactive dialog will start to set up credentials
    chat_auth = twitchaio.OAuth(USERNAME, "credentials.json", ["chat:read", "chat:edit"])

    # You can separate the credentials into multiple files: one for the bot account and one for the channel account
    # This is not necessary but can be helpful
    api_auth = twitchaio.OAuth(USERNAME, "api_credentials.json", [
        # This is just an example list and should be adjusted to your needs
        # For a complete list of possible scopes see the twitch documentation
        "channel:manage:polls", "channel:manage:predictions"
    ])

    api = twitchaio.API(api_auth, chat_auth)
    async with api:
        chat = twitchaio.Chat(chat_auth, CHANNEL)
        events = twitchaio.EventMonitor(api)

        # see https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types for details on available events and the data you receive
        # some of the events require special authorization so make sure the right scope is available on the api_auth object above
        @events.Event("stream.online", "1", {"broadcaster_user_id": api_auth.user_id})
        async def on_stream_live(data):
            event = data["event"]
            await chat.send_message(f"{event['broadcaster_user_name']} went live!", CHANNEL)

    pending = []
    try:
        _, pending = await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_EXCEPTION)
    except:
        for task in pending: task.cancel()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass