import discord
from discord.ext import commands
import bot_token
import logging

handler = logging.basicConfig(level=logging.INFO,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# bot = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")



@bot.command()
async def foo(ctx, arg):
    print(arg)
    await ctx.send(arg)


bot.run(bot_token.token, log_handler=handler)