from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx):
        """Owner only"""
        await self.bot.tree.sync()
        await ctx.send("Synced command tree to Discord.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Don't respond to random commands

        if isinstance(error, commands.NotOwner):
            await ctx.send("This command is reserved for ***High Exarch Kuelos***")
        else:
            await ctx.send(f"An error occurred: `{str(error)}`")

async def setup(bot):
    print("Loading Admin extension...")
    await bot.add_cog(Admin(bot))