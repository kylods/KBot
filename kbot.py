import os
import logging
import json
import random
import sys
import traceback
from dotenv import load_dotenv

import discord
from discord.ext import commands


# Initializes some global variables for the bot. Tokens, api keys, etc.
def load_config():
    config = {
        'discord_token': os.environ.get('DISCORD_TOKEN'),
        'default_prefix': os.environ.get('DEFAULT_PREFIX'),
        'spotify_id': os.environ.get('SPOTIFY_ID'),
        'spotify_secret': os.environ.get('SPOTIFY_SECRET')
    }

    if (not config['default_prefix'] or
    not config['discord_token'] or
    not config['spotify_id'] or
    not config['spotify_secret']):
        print("Environment variable(s) empty.")
        exit()

    return config
        
# Loads the .env environment variables, if it exists, then initializes the config dictionary
load_dotenv()
config = load_config()

# Initializes the intents for Discord to login with
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

# Initialize logger
handler = logging.basicConfig(level=logging.WARNING,
                              format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s', # Formats each log line
                              datefmt='%Y-%m-%d %H:%M:%S', # Custom date/time format for asctime
                              handlers=[logging.StreamHandler(), logging.FileHandler('kbot.log')], # Streamhandler will output to console, FileHandler outputs to kbot.log
                              )

# Initialize ./downloads/ and ./bot.server_data/
if not os.path.exists('downloads'):
    os.makedirs('downloads')
if not os.path.exists('servers'):
        os.makedirs('servers')


class Server():
    def __init__(self, guild_id):
        self.id = guild_id
        self.queue = []
        self.nowplaying = {}
        self.settings = {
            'prefix': config["default_prefix"],
            'loop': False,
            'playlists': {}
        }

    def enqueue(self, title, url):
        self.queue.append([title, url])
    
    def remove_from_queue(self, index=None):
        if self.queue:
            if index:
                if  0 <= index < len(self.queue):
                    removed = self.queue.pop(index)
                    return f"Removed **{removed[0]}** from the queue."
                else:
                    raise Exception("Index is outside of queue range.")
            else:
                self.queue = []
                return "Cleared the queue."

    def next_song(self):
        if self.queue:
            return self.queue.pop(0)
        return None

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

    def add_to_jukebox(self, alias, playlist):
        jukebox = self.get_jukebox()
        if alias in jukebox:
            raise Exception(f"{alias} already exists in the Jukebox.")
        if len(jukebox) >= 9:
            raise Exception(f"Jukebox is full. *Maximum of 9 playlists.*")
        jukebox[alias] = playlist
        self.save_settings()

    def remove_from_jukebox(self, alias):
        jukebox = self.get_jukebox()
        if not alias in jukebox:
            raise Exception(f"{alias} isn't in the Jukebox.")
        del jukebox[alias]
        self.save_settings()

    def get_jukebox(self):
        return self.settings['playlists']

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

def get_prefix(bot, message):
    """Returns a server's set 'prefix', or the bot's default_prefix if the server is not initialized."""
    if message.guild:
        if message.guild.id in bot.server_data:
            return bot.server_data[message.guild.id].settings.get('prefix')
    return config["default_prefix"]

def initialize_servers():
    """Initializes the Discord bot.server_data that the bot has access to, then recursively attempts to load each server's settings from './bot.server_data/'."""
    for guild in bot.guilds:
        print(f"Initializing {guild.name} with id {guild.id}")
        bot.server_data[guild.id] = Server(guild.id)
        bot.server_data[guild.id].load_settings()

bot = commands.Bot(command_prefix=get_prefix, intents=intents)
bot.server_data = {}
bot.config = config

async def update_status():
    await bot.change_presence(activity=discord.CustomActivity(name=f"Jukeboxing in {len(bot.server_data)} servers."))

@bot.event
async def on_ready():
    """Runs when the bot has initialized and authenticated with Discord."""
    print(f"Logged in as {bot.user}")

    # Scan for & load cog modules
    cogs = []
    cogsDir = os.listdir("cogs")
    for file in cogsDir:
        if file.endswith(".py"):
            cogs.append("cogs." + file[:-3])    

    for cog in cogs:
        try:
            await bot.load_extension(cog)
        except Exception as e:
            print(f"Failed to load extension {cog}.", file=sys.stderr)
            traceback.print_exc()

    # Load saved server configs & sets status
    initialize_servers()
    await update_status()

@bot.event
async def on_guild_join(guild):
    if not guild.id in bot.server_data:
        bot.server_data[guild.id] = Server(guild.id)
        bot.server_data[guild.id].load_settings()
    await update_status()

def main():
    bot.run(config["discord_token"], log_handler=handler)

main()