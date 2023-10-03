import discord
import bot_token
import logging

handler = logging.basicConfig(level=logging.INFO,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s',
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for logger
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    
    if message.author == bot.user:
        return
    else:
        print(f"({message.channel}) {message.author}: {message.content}")
    
    if message.content.startswith('!hello'):
        await message.channel.send('Hello!')


bot.run(bot_token.token, log_handler=handler)