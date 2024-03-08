import asyncio

USERNAME = "<username>"
CHANNEL = "<channel>" # can also be a list of channels
async def main():
    import twitchaio
    # It's fine if credentials.json doesn't exist, it'll be created on first run
    # On first boot an interactive dialog will start to set up credentials
    auth = twitchaio.OAuth(USERNAME, "credentials.json", ["chat:read", "chat:edit"])
    chat = twitchaio.Chat(auth, CHANNEL)
    commands = twitchaio.ChatCommands(chat)

    @commands.Command("!test")
    async def on_test_command(_):
        return "This text will be sent back to chat when the command is used"

    @commands.Command("!mod", user_level=twitchaio.UserLevel.Mod)
    async def on_mod_test_command(_):
        return "This text will only be sent if a the user is at least a mod"

    # message function argument can be used to make dynamic commands
    @commands.Command("!greet")
    async def greet_command(message : twitchaio.Chat.Message):
        return f"Hello {message.meta.display_name}"

    # general message callback can also be created, this will be called for all chat messages
    @chat.Message(twitchaio.tags.PRIVMSG.type)
    async def on_chat_message(message : twitchaio.Chat.Message):
        content = " ".join(message.content)
        print("Received message:", content)
        await chat.send_message(content.upper(), message.channel)

    pending = []
    try:
        _, pending = await asyncio.wait(asyncio.all_tasks(), return_when=asyncio.FIRST_EXCEPTION)
    except:
        for task in pending: task.cancel()

if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass