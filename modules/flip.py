import discord
import asyncio
from utils.dusk import command

class Flip:
    def __init__(self, amethyst):
        self.amethyst = amethyst
    
    @command()
    async def flip(self, ctx):
        """Flips 3 coins!"""
        yahtzee = discord.Embed()
        yahtzee.title = 'Flipping 3 coins...'
        yahtzee.set_image(url='https://a.pomf.cat/scoexz.png')
        yahtzee.color = 0xfaf500
        meme = await ctx.send(embed=yahtzee)
        await asyncio.sleep(5)
        nope = discord.Embed()
        nope.title = 'The results are in!'
        nope.set_image(url='https://a.pomf.cat/qnukau.png')
        nope.color = 0xfaf500
        nope.set_footer(text='None of the results are what you expected, Fuck you.')
        await meme.edit(embed=nope)

def setup(amethyst):
    return Flip(amethyst)