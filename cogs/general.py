from discord.ext import commands

class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    async def ping(self, ctx):
        """Returns KBot's latency to Discord."""
        await ctx.send(f"Pong! {int(self.bot.latency * 1000)}ms")
    
    @commands.hybrid_command()
    async def about(self, ctx):
        """Returns some info about KBot."""
        await ctx.send("Sah dood. I'm KBot, a Discord music bot by kuelos.")

    @commands.hybrid_command()
    async def setprefix(self, ctx, prefix):
        """Sets the current server's command prefix."""
        if not ctx.message.guild:
            return await ctx.send("This command can only be used in a server.")
        result = self.bot.server_data[ctx.guild.id].set_prefix(prefix)
        await ctx.send(result)

async def setup(bot):
    print("Loading General extension...")
    await bot.add_cog(General(bot))