from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command()
    @commands.is_owner()
    async def sync(self, ctx):
        await self.bot.tree.sync()
        await ctx.send("Synced command tree to Discord.")

    @commands.hybrid_command()
    @commands.is_owner()
    async def reload(self, ctx, extension):
        try:
            await self.bot.reload_extension(extension)
            await ctx.send(f"Reloaded extension `{extension}`")
        except Exception as e:
            await ctx.send(f"Failed to reload extension `{extension}`: `{e}`")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # Don't respond to random commands

        if isinstance(error, commands.NotOwner):
            await ctx.send("Sorry, you are not the owner of this bot!")
        else:
            await ctx.send(f"An error occurred: `{str(error)}`")

async def setup(bot):
    print("Loading Admin extension...")
    await bot.add_cog(Admin(bot))