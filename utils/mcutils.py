from typing import Tuple, List, Union
from datetime import datetime
import youtube_dl as ytdl
import discord
import asyncio
import aiohttp
import functools
import re
import concurrent.futures as ccf
import urllib.parse as urls

BASE_URI = 'https://connect.monstercat.com/api'
MONSTERCAT_ICON = 'https://assets.monstercat.com/essentials/logos/monstercat_logo_square_small.png'

MULTI_TYPES = ('Album', 'EP')
LONG_TYPES = ('Mixes', 'Podcast')

TRACKLIST_REGEX = re.compile(r'(?sm)(^(?:\d{2}:)?\d{2}:\d{2})\s(.*?)(?=(?:^\d{2}:\d{2}:\d{2}\s)|$)')  # Thanks Road
DURATION_REGEX = re.compile(r'^(?:\d{2}:)?\d{2}:\d{2}$')
PERFORMANCE_HORIZON_REGEX = re.compile(r'^(?:https?://)?prf.hn/click/camref:[\da-z]+/pubref:[\da-z]+/destination:.*$')
PERFORMANCE_HORIZON_DEST_REGEX = re.compile(r'destination:(.*)$')

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'audioformat': 'bestaudio/best',
    'quiet': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True
}

GENRE_COLOURS = {
    'Drum & Bass': 15866116,
    'Drumstep': 15933832,
    'Trap': 9178919,
    'Dubstep': 15211924,
    'Electronic': 12698049,
    'Glitch Hop': 759639,
    'House': 15371264,
    'Future Bass': 10131708,
    'Trance': 32487,
    'Indie Dance / Nu Disco': 1878963,
    'Synthwave': 1878963,
    'Electro': 15126016,
    'Happy Hardcore': 104192,
    'Hard Dance': 104192,
    'Moombahton': 759639
}

URL_REGEXES = {
    'Facebook': re.compile(r'^(?:https?://)?(?:www\.)?facebook\.com'),
    'SoundCloud': re.compile(r'^(?:https?://)?(?:www\.)?soundcloud\.com'),
    'Instagram': re.compile(r'^(?:https?://)?(?:www\.)?instagram\.com'),
    'YouTube': re.compile(r'^(?:https?://)?(?:(?:www\.|m.)?youtube\.com|youtu\.be)'),
    'Twitter': re.compile(r'^(?:https?://)?(?:www\.)?twitter\.com'),
    'Spotify': re.compile(r'^(?:https?://)?open\.spotify\.com'),
    'Beatport': re.compile(r'^(?:https?://)?(?:www\.)?beatport\.com'),
    'iTunes': re.compile(r'^(?:https?://)?itunes\.apple\.com'),
    'Mixcloud': re.compile(r'^(?:https?://)?(?:www\.)?mixcloud\.com'),
    'Bandcamp': re.compile(r'^(?:https?://)?music\.monstercat\.com'),
    'Google Play': re.compile(r'^(?:https?://)?play\.google\.com')
}
CATALOG_REGEXES = {
    'Album': re.compile(r'^MCUV-\d+$|^MC\d{3}$'),
    'Best of Compilation': re.compile(r'^MCB\d{3}$'),
    'Special Compilation': re.compile(r'^MCS\d{3}$'),
    '5 Year Anniversary Track': re.compile(r'^MCX004-\d$'),
    'Call of the Wild': re.compile(r'^COTW\d{3}$'),
    'Podcast': re.compile(r'^MCP\d{3}$'),
    'Rocket League Album': re.compile(r'^MCRL\d{3}$'),
    'Long Play': re.compile(r'^MCLP\d{3}$'),
    'Extended Play': re.compile(r'^MCEP\d{3}$'),
    'Free Download': re.compile(r'^MCF\d{3}$'),
    'Single': re.compile(r'^MCS\d{3}$')
}


def gen_duration(seconds: int) -> str:
    """Generate a human readable time from seconds."""
    if type(seconds) == float:
        seconds = round(seconds)

    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    return f'{hours:02}:{minutes:02}:{seconds:02}' if hours else f'{minutes:02}:{seconds:02}'


def parse_duration(dur: str) -> int:
    """Generates seconds from a human readable duration."""
    if not DURATION_REGEX.match(dur):
        raise ValueError('Time passed does not match required format: `XX:XX` or `XX:XX:XX`')

    parts = dur.split(':')
    seconds = 0

    if len(parts) == 3:
        seconds += int(parts[0]) * 60 * 60
        seconds += int(parts[1]) * 60
        seconds += int(parts[2])
    else:
        seconds += int(parts[0]) * 60
        seconds += int(parts[1])

    return seconds


def get_name(url: str) -> str:
    """Returns the formatted name for social media link."""
    name = [x for x, y in URL_REGEXES if y.search(url)]

    if name:
        return name[0]
    elif PERFORMANCE_HORIZON_REGEX.search(url):
        return urls.unquote(PERFORMANCE_HORIZON_DEST_REGEX.search(url).group(1))
    else:
        return url


def is_catalog_id(id: str) -> bool:
    """Checks if a given string matches a catalog ID."""
    return True if [x for x, y in CATALOG_REGEXES if y.match(id)] else False


def get_type_from_catalog_id(id: str) -> Union[str, None]:
    """Gets the type of a release from its catalog ID."""
    type = [x for x, y in CATALOG_REGEXES if y.match(id)]

    if type:
        return type[0]
    else:
        return None


def gen_search(search: str, *fields: List[str]) -> str:
    return '?fuzzyOr=' + ','.join(f'{x},{search}' for x in fields)


class ConnectGetter:
    def __init__(self, session=None):
        self.session = session or aiohttp.ClientSession()

    async def get_release(self, search: str, *, limit: int=10) -> Tuple[dict, List[dict]]:
        """
        Search for a release.
        Can either be a catalog ID, or name.
        """
        if type(search) != str:
            raise TypeError('search is not str.')
        elif not search:
            raise ValueError('Nothing to search.')

        if is_catalog_id(search.upper()):
            url = BASE_URI + f'/catalog/release/{search.upper()}'

            async with self.session.get(url) as r:
                if 200 <= r.status < 300:
                    data = await r.json()
                else:
                    raise ValueError(f'Invalid response code: `{r.status}`')

            if 'error' in data and data['message'] != 'The specified resource was not found.':
                raise ValueError(data['message'])
            elif 'error' in data:
                raise ValueError('Release not found.')

            url = BASE_URI + f"/catalog/release/{data['_id']}/tracks"

            async with self.session.get(url) as r:
                if 200 <= r.status < 300:
                    tracks = await r.json()
                else:
                    raise ValueError(f'Invalid response code: `{r.status}`')
        else:
            song = urls.quote(search.lower())
            search = gen_search(song, 'title', 'renderedArtists', 'catalogId')
            url = BASE_URI + f'/catalog/release{search}&limit={limit}'

            async with self.session.get(url) as r:
                if 200 <= r.status < 300:
                    data = await r.json()
                else:
                    raise ValueError(f'Invalid response code: `{r.status}`')

            if not data['results']:
                raise ValueError(f'No results found for `{search}`')

            data = data['results'][0]
            url = BASE_URI + f"/catalog/release/{data['_id']}/tracks"

            async with self.session.get(url) as r:
                if 200 <= r.status < 300:
                    tracks = await r.json()
                else:
                    raise ValueError(f'Invalid response code: `{r.status}`')

        return data, tracks['results']

    async def release_from_id(self, id: str) -> dict:
        if type(id) != str:
            raise TypeError('id is not str.')
        elif not id:
            raise ValueError('No id given.')

        url = BASE_URI + f'/catalog/release/{id}'

        async with self.session.get(url) as r:
            if 200 <= r.status < 300:
                data = await r.json()
            else:
                raise ValueError(f'Invalid response code: `{r.status}`')

        return data

    async def get_track(self, search: str, *, limit: int=10) -> dict:
        """
        Gets an individual track.
        This can be used to search for just an album's mix, rather than the entire album.
        """
        if type(search) != str:
            raise TypeError('search is not str.')
        elif not search:
            raise ValueError('Nothing to search.')

        track = urls.quote(search.lower().replace(' ', '-'))
        search = gen_search(track, 'title', 'artistsTitle')
        url = BASE_URI + f'/catalog/track{search}&limit={limit}'

        async with self.sesion.get(url) as r:
            if 200 <= r.status < 300:
                data = await r.json()
            else:
                raise ValueError(f'Invalid response code: {r.status}')

        if not data['results']:
            raise ValueError(f'No results for `{search}`')

        return data['results'][0]

    async def get_monstercat_track(self, search: str, *, limit: int=10, multi=False) -> Union[dict, List[dict]]:
        """
        Gets an individual track by Monstercat.
        Can be used for just getting mixes and podcasts.
        """
        if type(search) != str:
            raise TypeError('search is not str.')
        elif not search:
            raise ValueError('Nothing to search.')

        track = urls.quote(search.lower().replace(' ', '-'))
        url = BASE_URI + f'/catalog/track?fuzzy=title,{track},artistsTitle,monstercat&limit={limit}'

        async with self.sesion.get(url) as r:
            if 200 <= r.status < 300:
                data = await r.json()
            else:
                raise ValueError(f'Invalid response code: {r.status}')

        if not data['results']:
            raise ValueError(f'No results for `{search}`')

        if not multi:
            return data['results'][0]
        else:
            return data['results']

    async def get_artist(self, search: str, *, limit: int=10) -> Tuple[dict, List[dict]]:
        """Search for an artist."""
        if type(search) != str:
            raise TypeError('search is not str.')
        elif not str:
            raise ValueError('Nothing to search.')

        artist = urls.quote(search.lower().replace(' & ', '-').replace(' ', '-'))
        url = BASE_URI + f'/catalog/artist/{artist}'

        async with self.session.get(url) as r:
            if 200 <= r.status < 300:
                data = await r.json()
            else:
                raise ValueError(f'Invalid response code: `{r.status}`')

        if 'error' in data and data['message'] != 'Artist not found.':
            raise ValueError(data['message'])
        elif 'error' in data:
            artist = urls.quote(search)
            search = gen_search(artist, 'name', 'vanityUri')
            url = BASE_URI + f"/catalog/artist{search}&limit={limit}"

            async with self.session.get(url) as r:
                if 200 <= r.status < 300:
                    data = await r.json()
                else:
                    raise ValueError(f'Invalid response code: `{r.status}`')

            if not data['results']:
                raise ValueError('Artist not found.')
            else:
                data = data['results'][0]

        url = BASE_URI + f"/catalog/artist/{data['vanityUri']}/releases"

        async with self.session.get(url) as r:
            if 200 <= r.status < 300:
                releases = await r.json()
            else:
                raise ValueError(f'Invalid response code: `{r.status}`')

        return data, releases['results']


""" Audio Source Classes """


class MCSource(discord.AudioSource):
    """
    Base class for all Monstercat track sources to inherit from.
    Defines some base methods which should be implemented by any sources, as well as some default props.
    """

    def __init__(self, track):
        self.track = track
        self.executor = ccf.ThreadPoolExecutor(max_workers=4)
        self.loop = asyncio.get_event_loop()
        self._has_connect_data = False
        self.timestamp = datetime.now()

    async def get_info(self) -> None:
        """Fetches and loads data from appropriate sources."""
        raise NotImplementedError

    def set_connect_data(self, data: dict, tracks: List[dict]) -> None:
        """Sets data properties from data gotten from Connect."""
        raise NotImplementedError

    async def load(self) -> None:
        """Sets source to url."""
        raise NotImplementedError

    def info_embed(self) -> discord.Embed:
        """Returns an embed loaded with the relevant infomation."""
        raise NotImplementedError


class MCSingleSource(MCSource):
    """Audio source class for regular single tracks."""
    def __init__(self, track, data=None, tracks=None):
        super().__init__(track)
        self.type = 'single'
        self._data = data

        if data and tracks:
            self.set_connect_data(data, tracks)

    def __repr__(self):
        if not self._has_connect_data:
            return f'MCSingleSource(track="{self.track}", title=None, artists=None, duration=None)'
        else:
            return (f'MCSingleSource(track="{self.track}", title="{self.title}", artists="{self.artists}",'
                    f'duration="{self.duration}"')

    def __str__(self):
        return self.__repr__()

    async def get_info(self):
        if not self._has_connect_data:
            data, tracks = await ConnectGetter().get_release(self.track)
            self._data = data

            self.set_connect_data(data, tracks)

        if not hasattr(self, 'url'):
            if self._data and [x for x in self._data['urls'] if re.search(r'^(?:https?://)?(?:www\.)?youtube\.com', x)]:
                self.url = [x for x in self._data['urls'] if re.search(r'^(?:https?://)?(?:www\.)?youtube\.com', x)][0]

                del self._data
            else:
                with ytdl.YoutubeDL(YTDL_OPTS) as yt:
                    func = functools.partial(yt.extract_info, f'{self.artists} - {self.title}', download=False)

                data = await self.loop.run_in_executor(self.executor, func)

                if 'entries' in data:
                    data = data['entries'][0]

                self.url = data['webpage_url']

    def set_connect_data(self, data, tracks):
        if data['type'] in MULTI_TYPES:
            raise ValueError('Release detected to be an album, or album-like. Please use MCMultiSource.')
        elif data['type'] in LONG_TYPES:
            raise ValueError('Release detected to be long. Please use MCLongSource.')

        track = tracks[0]

        self.stream_url = f"https://s3.amazonaws.com/data.monstercat.com/blobs/{track['albums'][0]['streamHash']}"
        self.release_date = datetime.strptime(data['releaseDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
        self.title = data['title']
        self.artists = data['renderedArtists']
        self.thumb = data['coverUrl'].replace(' ', '%20') + '?image_width=256'
        self.bpm = round(track['bpm'])
        self.duration = round(track['duration'])
        self.genre = track.get('genre') or track['genres'][0]
        self._has_connect_data = True

    async def load(self):
        self.source = discord.FFmpegPCMAudio(self.stream_url)

    def read(self):
        return self.source.read()

    def cleanup(self):
        self.source.cleanup()

    def info_embed(self, ctx):
        embed = discord.Embed(title=f'{self.artists} - {self.title}', colour=GENRE_COLOURS.get(self.genre, 0),
                              description=f'[**Video Link**]({self.url})', timestamp=self.release_date)

        embed.set_thumbnail(url=self.thumb)
        embed.set_footer(text='MonstercatSingle', icon_url=MONSTERCAT_ICON)
        embed.set_author(name=ctx.msg.author.display_name, icon_url=ctx.msg.author.avatar_url_as(size=256))
        embed.add_field(name='BPM', value=self.bpm)
        embed.add_field(name='Duration', value=gen_duration(self.duration))

        return embed


class MCLongSource(MCSource):
    """Audio source class for long tracks, eg. podcasts and mixes."""
    def __init__(self, track):
        super().__init__(track)
        self.type = 'long'
        self._data = None
        self._has_yt_data = False

    def __repr__(self):
        if not self._has_connect_data:
            return f'MCLongSource(track="{self.track}", title=None, artists=None, duration=None, tracks=None)'
        else:
            return (f'MCLongSource(track="{self.track}", title="{self.title}", artists="{self.artists}",'
                    f'duration="{self.duration}"')

    def __str__(self):
        return self.__repr__()

    async def get_info(self):
        if not self._has_connect_data:
            getter = ConnectGetter()
            tracks = await getter.get_moonstercat_track(self.track, multi=True)

            if 'Podcast' in tracks[0]['title'] or 'Call of the Wild' in tracks[0]['title']:
                self.type = 'podcast'

                if 'Music Only' in tracks[0]['title']:
                    no_audio = [x for x in tracks if x['title'] == tracks[0]['title'].replace(' (Music Only)', '')]

                    if no_audio:
                        track = no_audio[0]
                    else:
                        track = tracks[9]
                else:
                    track = tracks[0]

                data = await getter.release_from_id(track['albums'][0]['albumId'])

                self.set_connect_data(data, track)
            else:
                self.type = 'album-mix'

                track = tracks[0]
                data = await getter.release_from_id(track['album'][0]['albumId'])

                self.set_connect_data(data, track)

        if not self._has_yt_data:
            with ytdl.YoutubeDL(YTDL_OPTS) as yt:
                func = functools.partial(yt.extract_info, f'{self.artists} - {self.title}', download=False)

            data = await self.loop.run_in_executor(self.executor, func)

            if 'entries' in data:
                data = data['entries'][0]

            self.set_yt_data(data)

    def set_connect_data(self, data, track):
        self.stream_url = f"https://s3.amazonaws.com/data.monstercat.com/blobs/{track['albums'][0]['streamHash']}"
        self.release_date = datetime.strptime(data['releaseDate'], '%Y-%m-%dT%H:%M:%S.%fZ')
        self.title = track['title']
        self.duration = track['duration']
        self.thumb = data['coverUrl'] + '?image_width=256'
        self.duration = round(track['duration'])
        self.catalog_id = data['catalogId']
        self._has_connect_data = True

    def set_yt_data(self, data):
        tracks = TRACKLIST_REGEX.findall(data['description'])
        tracks = [(parse_duration(x), y) for x, y in tracks]
        time = 0

        self.url = data['webpage_url']
        self.tracks = {}

        for stamp, name in tracks.values():
            old_time = time
            time += stamp
            self.tracks[stamp - old_time] = (name, stamp, stamp - old_time)

        self._has_yt_data = True

    async def load(self):
        self.source = discord.FFmpegPCMAudio(self.stream_url)

    async def start_loop(self, ctx):
        await ctx.send(embed=self.info_embed(ctx))

        for x, y

    def read(self):
        return self.source.read()

    def cleanup(self):
        self.source.cleanup()

    def info_embed(self, ctx):
        embed = discord.Embed(title=self.title, description=f'**{self.catalog_id}**\n[**Video Link**]({self.url})',
                              colour=16777215, timestamp=self.release_date)

        embed.set_thumbnail(url=self.thumb)
        embed.set_footer(text='MonstercatLong', icon_url=MONSTERCAT_ICON)
        embed.set_author(name=ctx.msg.author.display_name, icon_url=ctx.msg.author.avatar_url_as(size=256))
        embed.add_field(name='Tracks', value=len(self.tracks))
        embed.add_field(name='Duration', value=gen_duration(self.duration))

        return embed

    def track_embed(self, track):
        embed = discord.Embed(title=track[0], description=f'[**Timestamped Link**]({self.url}&t={track[1]}s)',
                              colour=16777215, timestamp=self.release_date)

        embed.set_thumbnail(url=self.thumb)
        embed.set_footer(text='MonstercatLong', icon_url=MONSTERCAT_ICON)
        embed.set_author(name=self.title + f' [{self.catalog_id}]')
        embed.add_field(name='Timestamp', value=gen_duration(track[2]))
        embed.add_field(name='Duration', value=gen_duration(track[1]))

        return embed