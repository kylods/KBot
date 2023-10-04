import os
import logging
import json
import asyncio
import random
from datetime import timedelta

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

def load_config():
    try:
        with open("config.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print("Config file not found. Please ensure you have a 'config.json' file.")
        exit()
    except json.JSONDecodeError:
        print("Error decoding the config file. Please ensure it's valid JSON.")
        exit()

config = load_config()
token = config["token"]
default_prefix = config["default_prefix"]

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
            'prefix': default_prefix,
            'loop': False,
            'vote_skip': True,
            'text_channel': None,
            'voice_channel': None,
            'dj_role': None,
            'skip_percentage': 50,
        }

    def enqueue(self, player):
        self.queue.append(player)
    
    def next_song(self):
        if self.queue:
            return self.queue.pop(0)
        return None
    
    def remove_from_queue(self, index=None):
        if self.queue:
            if index:
                if  0 <= index < len(self.queue):
                    removed = self.queue.pop(index)
                    return f"Removed {removed.title} from the queue"
                else:
                    raise Exception("Index is outside of queue range.")
            else:
                self.queue = []
                return "Cleared the queue."
        else:
            raise Exception("Queue is empty.")
        
    def promote(self, index):
        if self.queue:
            if 0 < index < len(self.queue):
                promoted_track = self.queue.pop(index)
                self.queue = [promoted_track] + self.queue
                return f"Promoted {promoted_track.title} to the top of the queue."
            elif 0 == index:
                raise Exception(f"{self.queue[index].title} is already at top of queue.")
            else:
                raise Exception("Index is outside of queue range.")
        else:
            raise Exception("Queue is empty.")
                
    def shuffle_queue(self):
        if self.queue:
            self.queue = random.shuffle(self.queue)
            return "Queue has been shuffled."
        else:
            raise Exception("Queue is empty.")

    def toggle_loop(self):
        if self.settings['loop']:
            self.settings['loop'] = False
            return "Disabled looping of the queue."
        else:
            self.settings['loop'] = True
            return "Enabled looping of the queue."
# in-memory server database
servers = {}

def get_prefix(bot, message):
    if message.guild:
        if message.guild.id in servers:
            return servers[message.guild.id].settings.get('prefix')
    return default_prefix

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

# Called when 
def _play_next_song(ctx):
    player = servers[ctx.guild.id].next_song()  # Dequeue the song
    if player:
        ctx.voice_client.play(player, after=lambda e: song_finished(ctx, e, player))
        servers[ctx.guild.id].nowplaying = {
            'title': player.title,
            'url': player.url,
            'length': timedelta(seconds=player.data.get('duration'))
        }
        asyncio.run_coroutine_threadsafe(ctx.send(f"Playing: **{player.title}**"), bot.loop)
    else:
        # Queue is empty, so clear now playing.
        if ctx.guild.id in servers:
            servers[ctx.guild.id].nowplaying = {}

# Called when a song finishes playing
def song_finished(ctx, error, player):
    if error:
        print(f"Player error: {error}")
    if servers[ctx.guild.id].settings['loop']:
        new_player = YTDLSource.from_url(player.url, loop=bot.loop)
        servers[ctx.guild.id].enqueue(new_player)
    _play_next_song(ctx)  # Play the next song in the queue

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.event
async def on_ready():
    """Runs when the bot has initialized and authenticated with Discord."""
    print(f"Logged in as {bot.user}")
    load_server_settings()

@bot.hybrid_command()
async def ping(ctx):
    """Returns KBot's latency to Discord."""
    await ctx.send(f"Pong! {int(bot.latency * 1000)}ms")

@bot.hybrid_command()
async def about(ctx):
    """Returns some info about KBot."""
    await ctx.send("Sah dood. I'm KBot, a Discord music bot by kuelos.")

@bot.command()
async def sync(ctx):
    await bot.tree.sync()

@bot.hybrid_command()
async def setprefix(ctx, prefix):
    """Sets the current server's command prefix."""
    if not ctx.message.guild:
        return await ctx.send("This command can only be used in a server.")
    if ctx.guild.id not in servers:
        servers[ctx.guild.id] = Server()
    servers[ctx.guild.id].settings['prefix'] = prefix
    save_server_settings(ctx.guild.id)  # Save only the settings of this specific server
    await ctx.send(f"Prefix set to `{prefix}` for this server!")

@bot.hybrid_command()
async def join(ctx):
    """Joins the user's active voice channel."""
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
    """Disconnects KBot from voice."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send('Disconnected.')

@bot.hybrid_command()
async def play(ctx, url):
    """Plays the given Youtube URL"""
    if not ctx.voice_client:
        success = await ctx.invoke(join)
        if not success:
            return

    if ctx.guild.id not in servers:
        servers[ctx.guild.id] = Server()

        player = await YTDLSource.from_url(url, loop=bot.loop)
        # clen = str(player.data.get('duration'))
        # player.url += '&range=0-' + clen
        servers[ctx.guild.id].enqueue(player)
        
        # Only start playing if the voice client is not currently playing.
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            _play_next_song(ctx)
        else:
            await ctx.send(f"**{player.title}** has been added to the queue!")

@bot.hybrid_command()
async def nowplaying(ctx):
    """Displays the currently playing song."""
    if ctx.guild.id in servers and servers[ctx.guild.id].nowplaying:
        np = servers[ctx.guild.id].nowplaying
        await ctx.send(f"Currently playing: **{np['title']}**\nURL: {np['url']}\nLength: {np['length']}")
    else:
        await ctx.send("No song is currently playing.")

@bot.hybrid_command()
async def queue(ctx):
    """Displays the song queue."""
    if ctx.guild.id in servers and servers[ctx.guild.id].queue:
        queued_songs = [f"{i+1}. **{song.title}**" for i, song in enumerate(servers[ctx.guild.id].queue)]
        await ctx.send("Current Queue:\n" + "\n".join(queued_songs))
    else:
        await ctx.send("The queue is empty.")

@bot.hybrid_command()
async def pause(ctx):
    """Pauses the current song."""
    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            await ctx.send("Playback has been paused.")
            await ctx.voice_client.pause()
        elif ctx.voice_client.is_paused():
            await ctx.send("Playback is already paused.")
        else:
            await ctx.send("Nothing is being played.")
    else:
        await ctx.send("Not currently playing music.")

@bot.hybrid_command()
async def resume(ctx):
    """Resumes playback."""
    if ctx.voice_client:
        if ctx.voice_client.is_paused():
            await ctx.send("Playback has been resumed.")
            await ctx.voice_client.resume()
        else:
            await ctx.send("Playback has not been paused.")
    else:
        await ctx.send("Not currently playing music.")

@bot.hybrid_command()
async def clear(ctx):
    """Clears the current queue."""
    if ctx.guild.id in servers:
        try:
            result = servers[ctx.guild.id].remove_from_queue()
            await ctx.send(result)
        except Exception as e:
            await ctx.send(e)

@bot.hybrid_command()
async def remove(ctx, index):
    """Removes a song from the queue with the given index."""
    if ctx.guild.id in servers:
        try:
            result = servers[ctx.guild.id].remove_from_queue(int(index) - 1)
            await ctx.send(result)
        except Exception as e:
            await ctx.send(e)

@bot.hybrid_command()
async def skip(ctx):
    """Skips the currently playing track."""
    if ctx.voice_client:
        if ctx.voice_client.is_playing():
            await ctx.send(f"Skipping {servers[ctx.guild.id].nowplaying['title']}.")
            ctx.voice_client.stop()
        else:
            ctx.send("Nothing is being played.")
    else:
        ctx.send("Not in a voice channel.")

@bot.hybrid_command(aliases=['playnext'])
async def promote(ctx, index):
    """Promotes the chosen index to the top of the queue."""
    if ctx.guild.id in servers:
        try:
            result = servers[ctx.guild.id].promote(int(index) - 1)
            await ctx.send(result)
        except Exception as e:
            await ctx.send(e)

@bot.hybrid_command()
async def shuffle(ctx):
    """Shuffles the queue."""
    if ctx.guild.id in servers:
        try:
            result = servers[ctx.guild.id].shuffle_queue()
            await ctx.send(result)
        except Exception as e:
            await ctx.send(e)

@bot.hybrid_command()
async def loop(ctx):
    """Toggles looping of the queue."""
    if ctx.guild.id in servers:
        result = servers[ctx.guild.id].toggle_loop()
        await ctx.send(result)

def main():
    bot.run(token, log_handler=handler)


main()