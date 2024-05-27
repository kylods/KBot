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

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing arguments. Use `/help (command)` for command usage.")

        else:
            await ctx.send(f"An unhandled error occurred. Ping Kuelos about this one. \n `{str(error.__class__.__name__)}`: `{str(error)}`")

    @commands.command()
    @commands.is_owner()
    async def reload(self, ctx, extension):
        """Reloads a specified module"""
        try:
            await self.bot.reload_extension(extension)
            await ctx.send(f"Reloaded extension `{extension}`")
        except Exception as e:
            await ctx.send(f"Failed to reload extension `{extension}`: `{e}`")

async def setup(bot):
    print("Loading Admin extension...")
    await bot.add_cog(Admin(bot))