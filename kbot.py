import os
import logging
import json
import random
import sys
import traceback

import discord
from discord.ext import commands


# Initializes some global variables for the bot. Tokens, api keys, etc.
def load_config():
    try:
        with open("config.json", "r") as file:
            config = json.load(file)
            if (config["discord_token"] == "YOUR_DISCORD_BOT_TOKEN" or
                config["spotify_id"] == "YOUR_SPOTIFY_ID" or
                config["spotify_secret"] == "YOUR_SPOTIFY_SECRET"):
                print("Config file not complete. Please add your Discord Bot Token & Spotify API info to config.json.")
                exit()
            else:
                return config
    except FileNotFoundError:
        config_data = {
            "discord_token": "YOUR_DISCORD_BOT_TOKEN",
            "default_prefix": "!",
            "spotify_id": "YOUR_SPOTIFY_ID",
            "spotify_secret": "YOUR_SPOTIFY_SECRET"
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
        os.makedirs('bot.server_data')


class Server():
    def __init__(self, guild_id):
        self.id = guild_id
        self.queue = []
        self.nowplaying = {}
        self.settings = {
            'prefix': config["default_prefix"],
            'loop': False
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

@bot.event
async def on_ready():
    """Runs when the bot has initialized and authenticated with Discord."""
    print(f"Logged in as {bot.user}")
    for cog in ["cogs.general", "cogs.admin", "cogs.music"]:
        try:
            await bot.load_extension(cog)
        except Exception as e:
            print(f"Failed to load extension {cog}.", file=sys.stderr)
            traceback.print_exc()
    initialize_servers()
    await bot.change_presence(activity=discord.CustomActivity(name=f"Jukeboxing in {len(bot.server_data)} servers."))

@bot.event
async def on_guild_join(guild):
    if not guild.id in bot.server_data:
        bot.server_data[guild.id] = Server(guild.id)
        bot.server_data[guild.id].load_settings()

@bot.command()
@commands.is_owner()
async def reload(ctx, extension):
    try:
        await bot.reload_extension(extension)
        await ctx.send(f"Reloaded extension `{extension}`")
    except Exception as e:
        await ctx.send(f"Failed to reload extension `{extension}`: `{e}`")

def main():
    bot.run(config["discord_token"], log_handler=handler)

main()