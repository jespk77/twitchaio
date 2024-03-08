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
        commands = twitchaio.ChatCommands(chat)

        @commands.Command("!prediction", cooldown=30)
        async def get_prediction(_):
            prediction_data = await api.get_prediction(limit=1)
            if prediction_data["data"]:
                prediction = prediction_data["data"][0]
                total_points = sum([outcome["channel_points"] for outcome in prediction["outcomes"]])
                for outcome in prediction["outcomes"]: outcome["percentage"] = round(
                    (outcome["channel_points"] / total_points) * 100, 2)

                index = 0
                outcome_text = " - ".join([
                                              f"{(index := index + 1)}: {outcome['title']} ({outcome['users']}x voted - {outcome['percentage']}% points)"
                                              for outcome in prediction["outcomes"]])
                prefix = "Last" if prediction["status"] == "RESOLVED" else "Current"
                return f"{prefix} prediction \"{prediction['title']}\": {outcome_text}"

    pending = []
    try:
        _, pending = await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_EXCEPTION)
    except:
        for task in pending: task.cancel()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass