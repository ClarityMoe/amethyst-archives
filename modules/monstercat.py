from utils.command_system import command, group
from utils.confirm import instance_guild
from utils import mcutils
from datetime import datetime
import discord


class Monstercat:
    def __init__(self, amethyst):
        self.amethyst = amethyst
        self.info_getter = mcutils.ConnectGetter(amethyst.session)
        self.queues = {}

    @command(aliases=['ids', 'catalogid', 'catalogids'])
    async def catalog(self, ctx):
        """Explains Monstercat catalog IDs, and what they mean."""
        await ctx.send('Monstercat has a set of different catalog IDs which are used to differentiate types of '
                       'releases, and when they were released in relation to each other.\n\n'
                       '**List of (Known) Catalog IDs**\n'
                       '*Any instances of `*` are meant to be a number (eg. MC\*\*\* could be MC025)*\n\n'
                       '**MCUV-\*** - Uncaged Albums\n'
                       '**MC\*\*\*** - Albums before Uncaged\n'
                       '**MCB\*\*\*** - Best of Compilations\n'
                       '**MCX\*\*\*** - "Special" Compilations\n'
                       '**MCX004-\*** - 5 Year Anniversary Track\n'
                       '**MCRL\*\*\*** - Rocket Leage Album\n'
                       '**MCLP\*\*\*** - Long Play (LP)\n'
                       '**MCEP\*\*\*** - Extended Play (EP)\n'
                       '**COTW\*\*\*** - Call of the Wild\n'
                       '**MCP\*\*\*** - Monstercat Podcast (before the rename to Call of the Wild)\n'
                       '**MCS\*\*\*** - Single\n'
                       '**MCF\*\*\*** - Free Download')

    @group()
    async def search(self, ctx):
        """Search for various Monstercat things."""
        await self.amethyst.send_command_help(ctx)

    @search.command(usage='<artist>')
    async def artist(self, ctx):
        """Search for an artist."""
        if not ctx.args:
            return await ctx.send('Please give me an artist to search for.')

        async with ctx.typing():
            data, releases = await self.info_getter.get_artist(ctx.suffix)

        # Construct embed from data
        # Any errors relating to getting valid data shouldn't happen here
        # If they do, please open an issue (you should regardless)

        description = discord.Embed.Empty

        if 'about' in data:
            description = data['about']

        embed = discord.Embed(title=data['name'], description=description)
        years = ', '.join(str(x) for x in sorted(y for y in data['years'] if y is not None))

        embed.set_thumbnail(url=data['profileImageUrl'].replace(' ', '%20'))
        embed.set_footer(text=f'Release years: {years}')

        if 'bookings' in data:
            embed.add_field(name='Bookings', value=data['bookings'].replace('Booking: ', ''), inline=False)

        if 'managementDetail' in data:
            embed.add_field(name='Management', value=data['managementDetail'].replace('Management: ', ''), inline=False)

        embed.add_field(name='Social Media', value=' '.join(f'**__[{mcutils.get_name(x)}]({x})__**' for x in
                        data['urls']), inline=False)
        embed.add_field(name='Releases', value=len(releases), inline=False)

        await ctx.send(embed=embed)

    @search.command(usage='<release>')
    async def release(self, ctx):
        """
        Search for a release.
        You can either use the name of the release, or use its catalog ID.
        """
        if not ctx.args:
            return await ctx.send('Please give me a release to search for.')

        async with ctx.typing():
            data, tracks = await self.info_getter.get_release(ctx.suffix)

        title = f"{data['renderedArtists']} - {data['title']}"
        description = mcutils.get_type_from_catalog_id(data['catalogId']) or data['type']
        timestamp = datetime.strptime(data['releaseDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
        links = ' '.join(f'**__[{mcutils.get_name(x)}]({x})__**' for x in data['urls'])
        embed = discord.Embed(title=title, description=description, timestamp=timestamp)

        embed.set_thumbnail(url=data['coverUrl'].replace(' ', '%20'))

        if links:
            embed.add_field(name='Links', value=links, inline=False)

        if len(tracks) > 1:
            # EP or album or something
            tracks_names = [f"{x['artistsTitle']} - {x['title']} **({mcutils.gen_duration(round(x['duration']))})**"
                            for x in tracks]
            tracks_joined = '\n'.join(tracks_names)

            embed.add_field(name='Duration', value=mcutils.gen_duration(round(sum(x['duration'] for x in tracks))))
            embed.add_field(name='Average BPM', value=round(sum(x['bpm'] for x in tracks) / len(tracks)))

            if len(tracks_joined) <= 1024:
                embed.add_field(name='Tracks', value=tracks_joined, inline=False)
            else:
                tracks1 = '\n'.join(tracks_names[:len(tracks_names) // 2])
                tracks2 = '\n'.join(tracks_names[len(tracks_names) // 2:])

                embed.add_field(name='Tracks - Part 1', value=tracks1, inline=False)
                embed.add_field(name='Tracks - Part 2', value=tracks2, inline=False)
        else:
            track = tracks[0]

            embed.add_field(name='Duration', value=mcutils.gen_duration(round(track['duration'])))
            embed.add_field(name='BPM', value=round(track['bpm']))

            if track['genres']:
                embed.add_field(name='Genre', value=track['genres'][0])

        await ctx.send(embed=embed)

    @group(aliases=['monstercat', 'mcm', 'mcmusic'])
    async def mc(self, ctx):
        await self.amethyst.send_command_help(ctx)

    @mc.command()
    @instance_guild()
    async def play(self, ctx):
        if not ctx.suffix:
            return await ctx.send('Please give me something to play.')

        if not ctx.msg.author.voice:
            return await ctx.send('You are not in a voice channel.')

        try:
            data, tracks = await self.info_getter.get_release(ctx.suffix)
        except Exception as e:
            return await ctx.send(str(e))

        source = mcutils.MCSingleSource(ctx.suffix, data, tracks)
        chan = await ctx.msg.author.voice.channel.connect()

        await source.get_info()
        await ctx.send(embed=source.info_embed)
        await source.load()

        async def after(err):
            if err:
                await chan.disconnect()
                raise err
            else:
                await chan.disconnect()

        chan.play(source, after=after)


def setup(amethyst):
    return Monstercat(amethyst)
