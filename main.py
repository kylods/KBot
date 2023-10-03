import os
import discord
from discord.ext import commands
import config
import logging
import json

handler = logging.basicConfig(level=logging.INFO,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class Server():
    def __init__(self):
        self.queue = []
        self.nowplaying = {}
        self.settings = {
            'prefix': '!',
            'loop': False,
            'vote_skip': True,
            'text_channel': None,
            'voice_channel': None,
            'dj_role': None
        }

# in-memory server database
servers = {}

def get_prefix(bot, message):
    if message.guild:
        if message.guild.id in servers:
            return servers[message.guild.id].settings.get('prefix')
    return '!'

def save_server_settings(guild_id=None):
    # Save the settings of each server (or a specific server) to individual files.
    # Args:
        # guild_id: Optional; the ID of a specific server to save. If not provided, all servers are saved.
    if not os.path.exists('servers'):
        os.makedirs('servers')

    if guild_id:  # Save only the specified server
        with open(f'servers/{guild_id}.json', 'w') as file:
            json.dump(servers[guild_id].settings, file)
    else:  # Save all servers
        for guild_id, server in servers.items():
            with open(f'servers/{guild_id}.json', 'w') as file:
                json.dump(server.settings, file)

def load_server_settings():
    if not os.path.exists('servers'):
        return
    
    for filename in os.listdir('servers'):
        if filename.endswith('.json'):
            guild_id = int(filename[:-5])
            with open(f'servers/{filename}', 'r') as file:
                if guild_id not in servers:
                    servers[guild_id] = Server()
                servers[guild_id].settings = json.load(file)

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    load_server_settings()

@bot.hybrid_command()
async def foo(ctx, arg):
    await ctx.send(arg)

@bot.hybrid_command()
async def ping(ctx):
    await ctx.send(f"Pong! {int(bot.latency * 1000)}ms")

@bot.hybrid_command()
async def about(ctx):
    await ctx.send("Sah dood. I'm KBot, a Discord music bot by kuelos.")

@bot.command()
async def sync(ctx):
    await bot.tree.sync()

@bot.command()
async def setprefix(ctx, prefix):
    # Command to set the custom prefix for a server.
    if not ctx.message.guild:
        return await ctx.send("This command can only be used in a server.")
    if ctx.guild.id not in servers:
        servers[ctx.guild.id] = Server()
    servers[ctx.guild.id].settings['prefix'] = prefix
    save_server_settings(ctx.guild.id)  # Save only the settings of this specific server
    await ctx.send(f"Prefix set to `{prefix}` for this server!")

def main():
    bot.run(config.token, log_handler=handler)


main()