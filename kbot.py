import os
import logging
import json
import asyncio
import random
import re
import math
import requests
import glob
from datetime import timedelta

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

# Initializes some global variables for the bot. Tokens, api keys, etc.
def load_config():
    try:
        with open("config.json", "r") as file:
            config = json.load(file)
            if config["discord_token"] and config["spotify_id"] and config["spotify_secret"]:
                return config
            else:
                print("Config file not complete. Please add your Discord Bot Token & Spotify API info to config.json.")
                exit()
    except FileNotFoundError:
        config_data = {
            "discord_token": "",
            "default_prefix": "!",
            "spotify_id": "",
            "spotify_secret": ""
        }

        # Write data to config.json
        with open('config.json', 'w') as json_file:
            json.dump(config_data, json_file, indent=4)

        print("Config file not found. Please add your Discord Bot Token & Spotify API info to config.json.")
        exit()
    except json.JSONDecodeError:
        print("Error decoding the config file. Please ensure it's valid JSON.")
        exit()

config = load_config()
discord_token = config["discord_token"]
default_prefix = config["default_prefix"]
spotify_id = config["spotify_id"]
spotify_secret = config["spotify_secret"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Initialize logger
handler = logging.basicConfig(level=logging.WARNING,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

# Initialize ./downloads/ and ./servers/
if not os.path.exists('downloads'):
    os.makedirs('downloads')
if not os.path.exists('servers'):
        os.makedirs('servers')

# Declaring ytdl search parameters
ytdl_opts = {'logger': handler,
             'format': 'bestaudio/bestaudio/best',  # Prioritize 128kbps audio
             'outtmpl': 'downloads/%(title)s.%(ext)s',  # Downloaded files will be saved in a 'downloads' folder
             'noplaylist': True
}
ytdl_search_opts = {'logger': handler,
                    'quiet': True,
                    'default_search': 'ytsearch',
                    'extract_flat': True,
                    'force_generic_extractor': True,
                    'ignoreerrors': True,
                    'skip_download': True
}

# Declare ytdl classes
ytdl_search = YoutubeDL(ytdl_search_opts)
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

        data['original_url'] = url
        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename), data=data)

class Server():
    def __init__(self, guild_id):
        self.id = guild_id
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

    def enqueue(self, title, url):
        self.queue.append([title, url])
    
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
                return f"Promoted {promoted_track[0]} to the top of the queue."
            elif 0 == index:
                raise Exception(f"{self.queue[index][0]} is already at top of queue.")
            else:
                raise Exception("Index is outside of queue range.")
        else:
            raise Exception("Queue is empty.")
                
    def shuffle_queue(self):
        if self.queue:
            random.shuffle(self.queue)
            return "Queue has been shuffled."
        else:
            raise Exception("Queue is empty.")

    def toggle_loop(self):
        if self.settings['loop']:
            self.settings['loop'] = False
            self.save_settings()
            return "Disabled looping of the queue."
        else:
            self.settings['loop'] = True
            self.save_settings()
            return "Enabled looping of the queue."

    def set_prefix(self, prefix):
        self.settings['prefix'] = prefix
        self.save_settings()
        return f"Command prefix set to `{prefix}` for this server!"

    def load_settings(self):
        filename = str(self.id) + '.json'
        if filename in os.listdir('servers'):
            file = open(f'servers/{filename}', 'r')
            self.settings = json.load(file)

    def save_settings(self):
        filename = str(self.id) + '.json'
        with open(f'servers/{filename}', 'w') as file:
            json.dump(self.settings, file)

# in-memory server database
servers = {}

def is_url(string):
    """Returns True if the given string is a valid URL."""
    url_pattern = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
    return re.match(url_pattern, string) is not None

def get_prefix(bot, message):
    """Returns a server's set 'prefix', or the bot's default_prefix if the server is not initialized."""
    if message.guild:
        if message.guild.id in servers:
            return servers[message.guild.id].settings.get('prefix')
    return default_prefix

def _play_next_song(ctx):
    """Called when a song should start playing. Calls song_finished() when the track finishes playing or is skipped."""
    song_info = servers[ctx.guild.id].next_song()  # Dequeue the next song & return its data
    if song_info:
        title, url = song_info
        if 'spotify' in url:
            url = get_youtube_url(title)
        async def play_song():
            player = await YTDLSource.from_url(url, loop=bot.loop)
            clen = str(player.data.get('duration')) 
            player.url += '&range=0-' + clen # This is a workaround for Youtube throttling
            ctx.voice_client.play(player, after=lambda e: song_finished(ctx, e, player))
            servers[ctx.guild.id].nowplaying = {
                'title': title,
                'url': url,
                'original_url': url,  # Now only storing original url
                'length': timedelta(seconds=player.data.get('duration'))
            }
            await ctx.send(f"Playing: **{title}**", delete_after=60, silent=True)
        asyncio.run_coroutine_threadsafe(play_song(), bot.loop)
    else:
        # Queue is empty, so clear now playing.
        if ctx.guild.id in servers:
            servers[ctx.guild.id].nowplaying = {}

def song_finished(ctx, error, player):
    """Called when a song finishes playing"""
    song_title = player.title
    player.cleanup()
    file_cleanup(song_title)
    if error:
        print(f"Player error: {error}")

    # Logic for servers who have 'loop' enabled.
    if servers[ctx.guild.id].settings['loop']:
        async def loop_song():
            servers[ctx.guild.id].enqueue(player.title, player.data['original_url'])
            _play_next_song(ctx)
        asyncio.run_coroutine_threadsafe(loop_song(), bot.loop)

    else:
        _play_next_song(ctx)

def file_cleanup(filename_base):
    """Deletes a played file from ./downloads/.
    This doesn't always work, perhaps exotic filenames or the file is still being accessed??"""
    search_pattern = os.path.join('downloads', f"{filename_base}.*")
    matching_files = glob.glob(search_pattern)

    for file in matching_files:
        os.remove(file)

async def extract_playlist_info(playlist_url):
    """Returns a list of videos from a given Youtube playlist URL."""
    # Get playlist info without downloading the videos
    playlist_info = await bot.loop.run_in_executor(None, lambda: ytdl_search.extract_info(playlist_url, download=False))

    if 'entries' not in playlist_info:
        return []

    # Extract video titles and URLs from the playlist info, filtering out privated & deleted videos
    videos = [
        {'title': entry['title'], 'url': entry['url']}
        for entry in playlist_info['entries'] 
        if entry['title'] not in ('[Private video]', '[Deleted video]')
    ]
    return videos

def get_spotify_token(client_id, client_secret):
    """Obtain an access token from Spotify's API."""
    auth_url = 'https://accounts.spotify.com/api/token'

    # Request based on Client Credentials Flow from Spotify's documentation
    response = requests.post(auth_url, {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
    })
    response_data = response.json()
    return response_data["access_token"]

def parse_spotify_link(url):
    """Returns a list of tracks from a given Spotify playlist, album, or track."""
    token = get_spotify_token(spotify_id, spotify_secret)
    headers = {
        "Authorization": f"Bearer {token}"
    }

    if "track" in url:
        # Extract ID from link
        match = re.search(r"track/(\w+)", url)
        if not match:
            raise Exception("Invalid Spotify track link!")
        track_id = match.group(1)

        # Get track's details from Spotify's API
        track_url = f"https://api.spotify.com/v1/tracks/{track_id}"
        response = requests.get(track_url, headers=headers)
        track_data = response.json()

        artist = track_data['artists'][0]['name']  # We take the name of the first artist
        title = track_data['name']
        return [f"{artist}, {title}"]
    
    elif "playlist" in url:
        # Extract playlist ID from link
        match = re.search(r"playlist/(\w+)", url)
        if not match:
            raise Exception("Invalid Spotify playlist link!")
        playlist_id = match.group(1)
        
        # Get tracks from the playlist
        playlist_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
        response = requests.get(playlist_url, headers=headers)
        playlist_data = response.json()
        
        tracks = []
        for item in playlist_data['items']:
            artist = item['track']['artists'][0]['name']
            title = item['track']['name']
            tracks.append(f"{artist}, {title}")
        return tracks

    elif "album" in url:
        # Extract album ID from link
        match = re.search(r"album/(\w+)", url)
        if not match:
            raise Exception("Invalid Spotify album link!")
        album_id = match.group(1)
        
        # Get tracks from the album
        album_url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
        response = requests.get(album_url, headers=headers)
        album_data = response.json()
        
        tracks = []
        for item in album_data['items']:
            artist = item['artists'][0]['name']
            title = item['name']
            tracks.append(f"{artist}, {title}")
        return tracks

    else:
        raise Exception("Invalid Spotify link!")

def get_youtube_url(query):
    """Returns the URL of the first search result of a given Youtube query."""
    search_result = ytdl_search.extract_info(f"ytsearch5:{query}", download=False)
    if search_result and 'entries' in search_result and len(search_result['entries']) > 0:
        # Get the URL of the first search result
        video_url = search_result['entries'][0]['url']
        return video_url
    else:
        print(f"No results found for '{query}'")
        return None

def initialize_servers():
    """Initializes the Discord servers that the bot has access to, then recursively attempts to load each server's settings from './servers/'."""
    for guild in bot.guilds:
        print(f"Initializing {guild.name} with id {guild.id}")
        servers[guild.id] = Server(guild.id)
        servers[guild.id].load_settings()

async def join_voice_channel(ctx):
    """Attempts to join a voice channel in the given 'context'.
    May raise an error with a message that may be sent as a Discord message.
    Otherwise, returns a string stating it has joined the voice channel."""
    # Check if the author is in a voice channel
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel
        permissions = channel.permissions_for(ctx.guild.me)
        
        # Check if the bot has the permission to join the voice channel
        if not permissions.connect:
            raise Exception(f"I don't have the permissions to join `{channel.name}`.")
        
        # Check if the bot is already in a voice channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()

        return (f"Joined `{channel.name}`!")
    else:
        raise Exception("You are not in a voice channel.")

async def process_query(ctx, query):
    """Processes a search query or URL in a given context."""
    # Check if the query is a URL
    if not is_url(query):
        # If it's not a URL, treat it as a search query
        URL = get_youtube_url(query)
        if URL:
            query = URL
        else:
            ctx.send(f"No results found for {query}")
        
    # From here, query should be validated as a URL
    if 'spotify' in query:
        try:
            tracks = parse_spotify_link(query)
            for track in tracks:
                servers[ctx.guild.id].enqueue(track, query)
            await ctx.send(f"{len(tracks)} tracks have been added to the queue!")
        except Exception as e:
            await ctx.send(e)
        return
    elif 'playlist?' in query:
        videos = await extract_playlist_info(query)
        for video in videos:
            servers[ctx.guild.id].enqueue(video['title'], video['url'])
        await ctx.send(f"{len(videos)} videos have been added to the queue!")
        return

    # At this point, the url isn't a Spotify link or a Youtube playlist
    player = await YTDLSource.from_url(query, loop=bot.loop)
    servers[ctx.guild.id].enqueue(player.title, query)
    await ctx.send(f"**{player.title}** has been added to the queue!")

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

@bot.event
async def on_ready():
    """Runs when the bot has initialized and authenticated with Discord."""
    print(f"Logged in as {bot.user}")
    initialize_servers()

@bot.event
async def on_guild_join(guild):
    if not guild.id in servers:
        servers[guild.id] = Server(guild.id)
        servers[guild.id].load_settings()

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
    result = servers[ctx.guild.id].set_prefix(prefix)
    await ctx.send(result)

@bot.hybrid_command()
async def join(ctx):
    """Joins the user's active voice channel."""
    try:
        message = await join_voice_channel(ctx)
        await ctx.send(message)
    except Exception as e:
        await ctx.send(e)

@bot.hybrid_command()
async def leave(ctx):
    """Disconnects KBot from voice."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send('Disconnected.')

@bot.hybrid_command()
async def play(ctx, *, query):
    """Plays the given Youtube URL, or plays the first search result of a query."""
    # Attempts to join a voice channel if not already in one. Otherwise, cancel execution.
    if not ctx.voice_client:
        try:
            await join_voice_channel(ctx)
        except Exception as e:
            await ctx.send(e)
            return

    async with ctx.typing():

        await process_query(ctx, query)
        
        # Only start playing if the voice client is not currently playing.
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
            _play_next_song(ctx)
            

@bot.hybrid_command(aliases=['playing', 'np'])
async def nowplaying(ctx):
    """Displays the currently playing song."""
    if ctx.guild.id in servers and servers[ctx.guild.id].nowplaying:
        np = servers[ctx.guild.id].nowplaying
        await ctx.send(f"Currently playing: **{np['title']}**\nURL: {np['url']}\nLength: {np['length']}")
    else:
        await ctx.send("No song is currently playing.")

@bot.hybrid_command()
async def queue(ctx, page: int = 1):
    """Displays the song queue."""
    if ctx.guild.id in servers and servers[ctx.guild.id].queue:
        max_pages = math.ceil(len(servers[ctx.guild.id].queue) / 10)
        if 0 < page <= max_pages:
            songs_in_page = servers[ctx.guild.id].queue[(page-1) * 10:page * 10]
        else:
            page = max_pages
            songs_in_page = servers[ctx.guild.id].queue[(page-1) * 10:page * 10]
        queued_songs = [f"{i+1 + (page - 1)*10}. [{song[0]}](<{song[1]}>)" for i, song in enumerate(songs_in_page)]
        await ctx.send(f"Current Queue: {len(servers[ctx.guild.id].queue)} items.\n" + "\n".join(queued_songs) + f"\nPage {page}/{max_pages}")
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

@bot.hybrid_command()
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

@bot.hybrid_command()
async def search(ctx, *, query):
    """Searches YouTube for the given query and returns a list of results."""
    
    # Use yt_dlp to search YouTube (this does not download the video)
    info_extracted = ytdl_search.extract_info(f"ytsearch5:{query}", download=False)
    if 'entries' not in info_extracted:
        await ctx.send("Couldn't find any results.")
        return
    
    entries = info_extracted['entries'][:5]
    results = [f"[{entry['title']}](<{entry['url']}>)" for entry in entries]
    
    # Format the results into a message
    msg = "Please select a song:\n" + "\n".join([f"**{i+1}**. {result}" for i, result in enumerate(results)])
    message = await ctx.send(msg)
    
    # Add number reactions to the message for selection
    for i in range(len(results)):
        await message.add_reaction(str(i+1) + "️⃣")
    
    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji)[0] in ["1", "2", "3", "4", "5"] and reaction.message.id == message.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("No selection made within 1 minute. Search cancelled.")
    else:
        index = int(str(reaction.emoji)[0]) - 1
        await play(ctx, query=entries[index]['url'])

@bot.hybrid_command()
async def stop(ctx):
    """Clears the queue and removes KBot from the voice channel."""
    if ctx.guild.id in servers:
        try:
            result = servers[ctx.guild.id].remove_from_queue()
        finally:
            if ctx.voice_client:
                if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                    ctx.voice_client.stop()
                await ctx.voice_client.disconnect()
            await ctx.send("Stopped playback.")
            return
    
@bot.hybrid_command()
async def playnext(ctx, *, query):
    if 'playlist?' in query or '/playlist/' in query or '/album/' in query:
        await ctx.send("Only individual tracks can be used with `playnext`")
        return
    await process_query(ctx, query)
    servers[ctx.guild.id].promote(len(servers[ctx.guild.id].queue) - 1)




def main():
    bot.run(discord_token, log_handler=handler)


main()