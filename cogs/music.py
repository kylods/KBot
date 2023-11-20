import asyncio
import glob
import logging
import math
import os
import re
import requests
from datetime import timedelta

import discord
from discord.ext import commands
from yt_dlp import YoutubeDL

# Initialize logger
handler = logging.basicConfig(level=logging.WARNING,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

# Declaring ytdl search parameters
ytdl_opts = {'logger': handler,
             'format': 'bestaudio/bestaudio/best',  # Prioritize 128kbps audio
             'outtmpl': 'downloads/%(title)s.%(ext)s',  # Downloaded files will be saved in a 'downloads' folder
             'noplaylist': True,
             'match_filter': lambda info_dict: "Livestream detected" if info_dict.get('is_live') else None,
}
ytdl_search_opts = {'logger': handler,
                    'quiet': True,
                    'default_search': 'ytsearch',
                    'extract_flat': True,
                    'force_generic_extractor': True,
                    'ignoreerrors': True,
                    'skip_download': True,
                    'match_filter': lambda info_dict: "Livestream detected" if info_dict.get('is_live') else None,
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
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=True))

        if 'entries' in data:
            data = data['entries'][0]

        data['original_url'] = url
        filename = ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member == self.bot.user:
            return
        if before.channel and self.bot.user in before.channel.members:
            if len(before.channel.members) == 1:
                await self._stop_playback(member.guild)
                

    @commands.hybrid_command()
    async def join(self, ctx):
        """Joins the user's active voice channel."""
        try:
            message = await _join_voice_channel(ctx)
            await ctx.send(message)
        except Exception as e:
            await ctx.send(e)

    @commands.hybrid_command()
    async def play(self, ctx, *, query):
        """Plays the given Youtube URL, or plays the first search result of a query."""
        # Attempts to join a voice channel if not already in one. Otherwise, cancel execution.
        if not ctx.voice_client:
            try:
                await _join_voice_channel(ctx)
            except Exception as e:
                await ctx.send(f"Error: {e}")
                return

        if ctx.voice_client.channel != ctx.author.voice.channel:
            await ctx.send(f"You are not in the same channel as KBot. Currently in {ctx.voice_client.channel}")
            return

        async with ctx.typing():

            await _process_query(ctx, self.bot, query)
            
            # Only start playing if the voice client is not currently playing.
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await _play_next_song(ctx, self.bot)


    @commands.hybrid_command(aliases=['playing', 'np'])
    async def nowplaying(self, ctx):
        """Displays the currently playing song."""
        if ctx.guild.id in self.bot.server_data and self.bot.server_data[ctx.guild.id].nowplaying:
            np = self.bot.server_data[ctx.guild.id].nowplaying
            await ctx.send(f"Currently playing: **{np['title']}**\nURL: {np['url']}\nLength: {np['length']}")
        else:
            await ctx.send("No song is currently playing.")

    @commands.hybrid_command()
    async def queue(self, ctx, page: int = 1):
        """Displays the song queue."""
        if ctx.guild.id in self.bot.server_data and self.bot.server_data[ctx.guild.id].queue:
            max_pages = math.ceil(len(self.bot.server_data[ctx.guild.id].queue) / 10)
            if 0 < page <= max_pages:
                songs_in_page = self.bot.server_data[ctx.guild.id].queue[(page-1) * 10:page * 10]
            else:
                page = max_pages
                songs_in_page = self.bot.server_data[ctx.guild.id].queue[(page-1) * 10:page * 10]
            queued_songs = [f"{i+1 + (page - 1)*10}. [{song[0]}](<{song[1]}>)" for i, song in enumerate(songs_in_page)]
            await ctx.send(f"Current Queue: {len(self.bot.server_data[ctx.guild.id].queue)} items.\n" + "\n".join(queued_songs) + f"\nPage {page}/{max_pages}")
        else:
            await ctx.send("The queue is empty.")

    @commands.hybrid_command()
    async def pause(self, ctx):
        """Pauses the current song."""
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                await ctx.send("Playback has been paused.")
                ctx.voice_client.pause()
            elif ctx.voice_client.is_paused():
                await ctx.send("Playback is already paused.")
            else:
                await ctx.send("Nothing is being played.")
        else:
            await ctx.send("Not currently playing music.")

    @commands.hybrid_command()
    async def resume(self, ctx):
        """Resumes playback."""
        if ctx.voice_client:
            if ctx.voice_client.is_paused():
                await ctx.send("Playback has been resumed.")
                ctx.voice_client.resume()
            else:
                await ctx.send("Playback has not been paused.")
        else:
            await ctx.send("Not currently playing music.")

    @commands.hybrid_command()
    async def clear(self, ctx):
        """Clears the current queue."""
        if ctx.guild.id in self.bot.server_data:
            try:
                result = self.bot.server_data[ctx.guild.id].remove_from_queue()
                await ctx.send(result)
            except Exception as e:
                await ctx.send(e)

    @commands.hybrid_command()
    async def remove(self, ctx, index):
        """Removes a song from the queue with the given index."""
        if ctx.guild.id in self.bot.server_data:
            try:
                result = self.bot.server_data[ctx.guild.id].remove_from_queue(int(index) - 1)
                await ctx.send(result)
            except Exception as e:
                await ctx.send(e)

    @commands.hybrid_command()
    async def skip(self, ctx):
        """Skips the currently playing track."""
        if ctx.voice_client:
            if ctx.voice_client.is_playing():
                await ctx.send(f"Skipping {self.bot.server_data[ctx.guild.id].nowplaying['title']}.")
                ctx.voice_client.stop()
            else:
                await ctx.send("Nothing is being played.")
        else:
            await ctx.send("Not in a voice channel.")

    @commands.hybrid_command()
    async def promote(self, ctx, index):
        """Promotes the chosen index to the top of the queue."""
        if ctx.guild.id in self.bot.server_data:
            try:
                result = self.bot.server_data[ctx.guild.id].promote(int(index) - 1)
                await ctx.send(result)
            except Exception as e:
                await ctx.send(e)

    @commands.hybrid_command()
    async def shuffle(self, ctx):
        """Shuffles the queue."""
        if ctx.guild.id in self.bot.server_data:
            try:
                result = self.bot.server_data[ctx.guild.id].shuffle_queue()
                await ctx.send(result)
            except Exception as e:
                await ctx.send(e)

    @commands.hybrid_command()
    async def loop(self, ctx):
        """Toggles looping of the queue."""
        if ctx.guild.id in self.bot.server_data:
            result = self.bot.server_data[ctx.guild.id].toggle_loop()
            await ctx.send(result)

    @commands.hybrid_command()
    async def search(self, ctx, *, query):
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
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("No selection made within 1 minute. Search cancelled.")
        else:
            index = int(str(reaction.emoji)[0]) - 1
            await self.play(ctx, query=entries[index]['url'])

    @commands.hybrid_command(aliases=['leave'])
    async def stop(self, ctx):
        """Clears the queue and removes KBot from the voice channel."""
        if ctx.voice_client:
            await self._stop_playback(ctx.guild)
            await ctx.send("Stopped playback.")

        
    @commands.hybrid_command()
    async def playnext(self, ctx, *, query):
        if 'playlist?' in query or '/playlist/' in query or '/album/' in query:
            await ctx.send("Only individual tracks can be used with `playnext`")
            return
        await _process_query(ctx, self.bot, query)
        self.bot.server_data[ctx.guild.id].promote(len(self.bot.server_data[ctx.guild.id].queue) - 1)

    async def _stop_playback(self, guild: discord.Guild):
        if guild.id in self.bot.server_data:
            self.bot.server_data[guild.id].remove_from_queue()

        if guild.voice_client:
            if guild.voice_client.is_playing() or guild.voice_client.is_paused():
                guild.voice_client.stop()
            await guild.voice_client.disconnect()

    @commands.hybrid_command()
    async def jukebox(self, ctx, arg1='', arg2='', arg3=''):
        """Adds a track or playlist to the server's Jukebox, storing the URL for anyone to easily access."""
        server = self.bot.server_data[ctx.guild.id]
        match arg1:
            case 'add':
                if arg2 and arg3:
                    try:
                        server.add_to_jukebox(arg2, arg3)
                        await ctx.send(f"Added {arg2} to this server's *jukebox*!")
                    except Exception as e:
                        await ctx.send(e)
                else:
                    await ctx.send("Invalid arguments. `jukebox add <alias> <URL>`")
            case 'remove':
                if arg2:
                    try:
                        server.remove_from_jukebox(arg2)
                        await ctx.send(f"Removed {arg2} from this server's *jukebox*.")
                    except Exception as e:
                        await ctx.send(e)
                else:
                    await ctx.send("Invalid arguments. `jukebox remove <alias>`")
            case '':
                jukebox = server.get_jukebox()
                playlists = []
                for key in jukebox:
                    playlists.append(key)

                # Check if there are playlists in jukebox
                if len(jukebox) == 0:
                    await ctx.send("This server's *Jukebox* is empty.")

                # Format the jukebox list into a message
                msg = "**Select a playlist:**\n" + "\n".join([f"**{i+1}**. [{key}](<{jukebox[key]}>)" for i, key in enumerate(playlists)])
                message = await ctx.send(msg, delete_after=60)
                
                # Add number reactions to the message for selection
                for i in range(len(jukebox)):
                    await message.add_reaction(str(i+1) + "️⃣")
                
                def check(reaction, user):
                    return user == ctx.author and str(reaction.emoji)[0] in ["1", "2", "3", "4", "5", "6", "7", "8", "9"] and reaction.message.id == message.id

                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.TimeoutError:
                    await ctx.send("No selection made.", delete_after=60)
                else:
                    index = int(str(reaction.emoji)[0]) - 1
                    await self.play(ctx, query=jukebox[playlists[index]])
            case _:
                await ctx.send("Unknown operator for `jukebox`. Use `jukebox add`, `jukebox remove`, or `jukebox`")
        


async def _extract_playlist_info(bot, playlist_url):
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

def _get_spotify_token(client_id, client_secret):
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

def _parse_spotify_link(bot, url):
    """Returns a list of tracks from a given Spotify playlist, album, or track."""
    token = _get_spotify_token(bot.config["spotify_id"], bot.config["spotify_secret"])
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
        
        # Get tracks from the playlist, iterating if theres multiple pages
        tracks = []
        playlist_url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"

        while playlist_url:
            response = requests.get(playlist_url, headers=headers)
            playlist_data = response.json()
            
            for item in playlist_data['items']:
                artist = item['track']['artists'][0]['name']
                title = item['track']['name']
                tracks.append(f"{artist}, {title}")
            playlist_url = playlist_data['next']
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



async def _join_voice_channel(ctx):
    """Attempts to join a voice channel in the given 'context'.
    May raise an error if the author isn't in a voice channel, or if the bot has insufficient permissions to join.
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

async def _process_query(ctx, bot, query):
    """Processes a search query or URL in a given context."""
    # Check if the query is a URL
    if not _is_url(query):
        # If it's not a URL, treat it as a search query
        url = _get_youtube_url(query)
        if url:
            query = url
        else:
            ctx.send(f"No results found for {query}")
        
    # From here, query should be validated as a URL
    if 'spotify' in query:
        try:
            tracks = _parse_spotify_link(bot, query)
            for track in tracks:
                bot.server_data[ctx.guild.id].enqueue(track, query)
            await ctx.send(f"{len(tracks)} tracks have been added to the queue!")
        except Exception as e:
            await ctx.send(e)
        return
    elif 'playlist?' in query:
        videos = await _extract_playlist_info(bot, query)
        for video in videos:
            bot.server_data[ctx.guild.id].enqueue(video['title'], video['url'])
        await ctx.send(f"{len(videos)} videos have been added to the queue!")
        return
    else:
        # At this point, the url isn't a Spotify link or a Youtube playlist
        player = await YTDLSource.from_url(query, loop=bot.loop)
        bot.server_data[ctx.guild.id].enqueue(player.title, query)
        await ctx.send(f"**{player.title}** has been added to the queue!")
    
def _is_url(string):
    """Returns True if the given string is a valid URL."""
    url_pattern = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+")
    return re.match(url_pattern, string) is not None

def _file_cleanup(filename_base):
    """Deletes a played file from ./downloads/.
    This doesn't always work, perhaps exotic filenames or the file is still being accessed??"""
    search_pattern = os.path.join('downloads', f"{filename_base}.*")
    matching_files = glob.glob(search_pattern)

    for file in matching_files:
        os.remove(file)


async def _song_finished(ctx, bot, error, player):
    """Called when a song finishes playing"""
    song_title = player.title
    player.cleanup()
    _file_cleanup(song_title)
    if error:
        print(f"Player error: {error}")

    # Logic for servers who have 'loop' enabled.
    if bot.server_data[ctx.guild.id].settings['loop']:
        async def loop_song():
            bot.server_data[ctx.guild.id].enqueue(player.title, player.data['original_url'])
            await _play_next_song(ctx, bot)
        await loop_song()
    else:
        await _play_next_song(ctx, bot)

def _get_youtube_url(query):
    """Returns the URL of the first search result of a given Youtube query."""
    search_result = ytdl_search.extract_info(f"ytsearch5:{query}", download=False)
    if search_result and 'entries' in search_result and len(search_result['entries']) > 0:
        # Get the URL of the first search result
        video_url = search_result['entries'][0]['url']
        return video_url
    else:
        print(f"No results found for '{query}'")
        return None

async def _play_next_song(ctx, bot):
    """Called when a song should start playing. Calls song_finished() when the track finishes playing or is skipped."""
    song_info = bot.server_data[ctx.guild.id].next_song()  # Dequeue the next song & return its data

    if not song_info:
        # Queue is empty, so clear now playing.
        if ctx.guild.id in bot.server_data:
            bot.server_data[ctx.guild.id].nowplaying = {}
            return
    
    title, url = song_info
    if 'spotify' in url:
        url = _get_youtube_url(title)

    player = await YTDLSource.from_url(url, loop=bot.loop)

    async def after_callback(ctx, e, player):
        await _song_finished(ctx, bot, e, player)

    def after_lambda(e):
        # Invoke the asynchronous callback using the event loop
        loop = bot.loop
        loop.create_task(after_callback(ctx, e, player))

    async def play_song():
        clen = str(player.data.get('duration')) 
        player.url += '&range=0-' + clen # This is a workaround for Youtube throttling
        ctx.voice_client.play(player, after=after_lambda)
        bot.server_data[ctx.guild.id].nowplaying = {
            'title': title,
            'url': url,
            'original_url': url,  # Now only storing original url
            'length': timedelta(seconds=player.data.get('duration'))
        }
        await ctx.send(f"Playing: **{title}**", delete_after=60, silent=True)
    await play_song()



async def setup(bot):
    print("Loading Music extension...")
    await bot.add_cog(Music(bot))