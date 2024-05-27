from discord.ext import commands
from flask import Flask, request
import asyncio

app = Flask(__name__)

class API(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.server = None

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.server:
            self.server = app.run(host='0.0.0.0', port=5000, use_reloader=False)

    @app.route('/message', methods=['POST'])
    def send_message(self):
        data = request.json
        channel = self.bot.get_channel(data['channel_id'])
        if channel:
            asyncio.run_coroutine_threadsafe(
                channel.send(data['message']),
                self.bot.loop
            )
            return {'status': 'success'}, 200
        return {'error': 'Channel not found'}, 404
    
    @app.route('/channels', methods=['GET'])
    def get_channels(self):
        channels = self.bot.get_all_channels()
        output = []
        for ch in channels:
            output.append(ch.name)
        return output, 200

    
def setup(bot):
    print("Loading Web API extension...")
    bot.add_cog(API(bot))