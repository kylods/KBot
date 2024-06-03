from discord.ext import commands
import discord
from quart import Blueprint, Quart, request, jsonify
import asyncio

# init api object
api = Blueprint('api', __name__, url_prefix='/api')


class API(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.define_routes()
        self.quart = Quart(__name__)
        self.quart.register_blueprint(api)
        self.quart.bot = bot
        self.webserver_task = None
        self.bot.loop.create_task(self.start_quart())

    async def start_quart(self):
        if self.webserver_task and not self.webserver_task.done():
            self.webserver_task.cancel()
            try:
                await self.webserver_task
            except asyncio.CancelledError:
                pass
        self.webserver_task = asyncio.create_task(self.quart.run_task(host='0.0.0.0', port=5000))

    def define_routes(self):
        @api.route('/guilds/channels/message', methods=['POST'])
        async def send_message():
            data = await request.get_json()
            channel = self.bot.get_channel(data['channel_id'])
            if channel:
                asyncio.run_coroutine_threadsafe(
                    channel.send(data['message']),
                    self.bot.loop
                )
                return jsonify({'status': 'success'}), 200
            return jsonify({'error': 'Channel not found'}), 404

        @api.route('/guilds', methods=['GET'])
        async def get_guilds():
            guilds = self.bot.guilds
            output = []
            for g in guilds:
                output.append({"name": g.name, "id": g.id})
            return jsonify(output), 200
        
        @api.route('/guilds/channels', methods=['GET'])
        async def get_channels_by_guild():
            data = await request.get_json()
            output = []
            try:
                guild: discord.Guild = await self.bot.fetch_guild(data['guild_id'])
                channels = await guild.fetch_channels()
                for ch in channels:
                    if isinstance(ch, discord.TextChannel):
                        output.append({"name": ch.name, "id": ch.id})
                return jsonify(output), 200

            except Exception as e:
                print(e)
                return jsonify(output), 404            
        
        @api.route('/guilds/player', methods=['GET'])
        async def get_guild_player():
            data = await request.get_json()
            guild: discord.Guild = self.bot.fetch_guild(data['guild_id'])
            output = {
                "active": False,
                "title": None,
                "length": None,
                "current_time": None,
                "url": None
                }
            np = self.bot.server_data[data['guild_id']].music.now_playing
            if np:
                output['active'] = True
                output['title'] = np['title']
                output['length'] = str(np['length'])
                output['url'] = np['url']
            return output, 200

    def cog_unload(self):
        if self.webserver_task and not self.webserver_task.done():
            self.webserver_task.cancel()

async def setup(bot):
    print("Loading Web API extension...")
    await bot.add_cog(API(bot))