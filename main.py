import os
import config
import logging
import json
import discord
from discord.ext import commands
from yt_dlp import YoutubeDL
import asyncio
from datetime import timedelta

handler = logging.basicConfig(level=logging.INFO,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

if not os.path.exists('downloads'):
    os.makedirs('downloads')

ytdl_opts = {'logger': handler,
             'format': 'bestaudio[abr=128]/bestaudio/best',  # Prioritize 128kbps audio
             'outtmpl': 'downloads/%(title)s.%(ext)s',  # Downloaded files will be saved in a 'downloads' folder
}

ytdl = YoutubeDL(ytdl_opts)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data):
        super().__init__(source)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=True))

        if 'entries' in data:
            data = data['entries'][0]

        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename), data=data)


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
            'dj_role': None,
            'skip_percentage': 50,
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

@bot.hybrid_command()
async def join(ctx):
    # Check if the author is in a voice channel
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.guild.me)
        
        # Check if the bot has the permission to join the voice channel
        if not permissions.connect:
            await ctx.send(f"I don't have the permissions to join `{channel.name}`.")
            return False
        
        # Check if the bot is already in a voice channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()

        await ctx.send(f"Joined `{channel.name}`!")
        return True
    else:
        await ctx.send("You are not in a voice channel.")
        return False

@bot.hybrid_command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()

@bot.hybrid_command()
async def play(ctx, url):
    if not ctx.voice_client:
        success = await ctx.invoke(join)  # Join user's voice channel if not in one
        if not success:
            return

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop)
    #    clen = str(player.data.get('duration'))
    #    player.url += '&range=0-' + clen # This fixes youtube throttling download speed. dont ask me why this works
        ctx.voice_client.play(player, after=lambda e: song_finished(ctx, e))
        await ctx.send(f"Playing: **{player.title}**")

        if ctx.guild.id not in servers:
            servers[ctx.guild.id] = Server()
        servers[ctx.guild.id].nowplaying = {
            'title': player.title,
            'url': url,
            'length': timedelta(seconds = player.data.get('duration'))  # this gets the duration from the ytdl data
        }
        
        await ctx.send(f"Playing: **{player.title}**")

def song_finished(ctx, error):
    if error:
        print(f"Player error: {error}")

    # Clear the nowplaying variable when the song finishes
    if ctx.guild.id in servers:
        servers[ctx.guild.id].nowplaying = {}

@bot.hybrid_command()
async def nowplaying(ctx):
    if ctx.guild.id in servers and servers[ctx.guild.id].nowplaying:
        np = servers[ctx.guild.id].nowplaying
        await ctx.send(f"Currently playing: **{np['title']}**\nURL: {np['url']}\nLength: {np['length']}")
    else:
        await ctx.send("No song is currently playing.")

def main():
    bot.run(config.token, log_handler=handler)


main()