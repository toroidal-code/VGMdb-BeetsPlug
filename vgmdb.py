"""Adds VGMdb search support to Beets
"""
from beets.autotag.hooks import AlbumInfo, TrackInfo, Distance
from beets.plugins import BeetsPlugin
from six.moves import urllib
import sys
import requests
import re

LANG_MAP = { 'ja': 'Japanese', 'ja-latn': 'Romaji', 'en': 'English' }


class VGMdbPlugin(BeetsPlugin):
    def __init__(self):
        super(VGMdbPlugin, self).__init__()
        self.config.add({
            'source_weight': 1.0,
            'lang-priority': 'ja, en, ja-latn'
        })
        self._log.debug('Querying VGMdb')
        self.source_weight = self.config['source_weight'].as_number()
        self.lang = self.config['lang-priority'].get().split(",")

    def album_distance(self, items, album_info, mapping):
        """Returns the album distance.
        """
        dist = Distance()
        if album_info.data_source == 'VGMdb':
            dist.add('source', self.source_weight)
        return dist

    def candidates(self, items, artist, album, va_likely):
        """Returns a list of AlbumInfo objects for VGMdb search results
        matching an album and artist (if not various).
        """
        try:
            return self.get_albums(album, va_likely)
        except:
            self._log.debug('VGMdb Search Error: (query: %s)' % query)
            return []

    def album_for_id(self, album_id):
        """Fetches an album by its VGMdb ID and returns an AlbumInfo object
        or None if the album is not found.
        """
        id = album_id.split(':')
        if len(id) > 1 and 'vgmdb' not in id:
            return
        elif len(id) > 1 and 'vgmdb' in id:
            album_id = id[1]

        self._log.debug('Querying VGMdb for release %s' % str(album_id))

        # Get from VGMdb
        r = requests.get('http://vgmdb.info/album/%s?format=json' % str(album_id))

        # Decode Response's content
        try:
            item = r.json()
        except:
            self._log.debug('VGMdb JSON Decode Error: (id: %s)' % album_id)
            return None

        return self.get_album_info(item, False)

    def get_albums(self, query, va_likely):
        """Returns a list of AlbumInfo objects for a VGMdb search query.
        """
        # Strip non-word characters from query. Things like "!" and "-" can
        # cause a query to return no results, even if they match the artist or
        # album title. Use `re.UNICODE` flag to avoid stripping non-english
        # word characters.
        query = re.sub(r'(?u)\W+', ' ', query)
        # Strip medium information from query, Things like "CD1" and "disk 1"
        # can also negate an otherwise positive result.
        query = re.sub(r'(?i)\b(CD|disc)\s*\d+', '', query)

        # Query VGMdb
        r = requests.get('http://vgmdb.info/search/albums/%s?format=json' % urllib.parse.quote(query.encode('utf-8')))

        # Decode Response's content
        try:
            items = r.json()
        except:
            self._log.debug('VGMdb JSON Decode Error: (query: %s)' % query)
            return []

        # Break up and get search results

        return [self.album_for_id(item["link"].split('/')[-1])
                for item in items["results"]["albums"]]

    def get_album_info(self, item, va_likely):
        """Convert json data into a format beets can read
        """
        # If a preferred lang is available use that instead
        album_name = item["name"]
        for lang in self.lang:
            if lang in item["names"]:
                album_name = item["names"][lang]
                break

        album_id = int(item["link"].split('/')[-1])
        catalognum = item["catalog"]

        # Get Artist information
        if "performers" in item and item["performers"] and not len(item["performers"]) > 1:
            artist_type = "performers"
        elif "organizations" in item and item["organizations"]:
            artist_type = "organizations"
        else:
            artist_type = "composers"

        artists = []
        for artist in item[artist_type]:
            a = ''
            for lang in self.lang:
                if lang in artist["names"]:
                    a = artist["names"][lang]
                    break
            if not a:
                a = artist["names"].itervalues().next()
            artists.append(a)

        artist = artists[0]

        if "link" in item[artist_type][0]:
            artist_id = item[artist_type][0]["link"].split('/')[-1]
        else:
            artist_id = None

        # Get Track metadata
        tracks = []
        total_index = 0
        for disc_index, disc in enumerate(item["discs"]):
            for track_index, track in enumerate(disc["tracks"]):
                total_index += 1

                title = None
                for lang in self.lang:
                    if lang in LANG_MAP and LANG_MAP[lang] in track["names"]:
                        title = track["names"][LANG_MAP[lang]]
                        break

                if not title:
                    title = track["names"].values()[0]

                index = total_index

                if track["track_length"] == "Unknown":
                    length = 0
                else:
                    length = track["track_length"].split(":")
                    length = (float(length[0]) * 60) + float(length[1])

                media = item["media_format"]
                medium = disc_index + 1
                medium_index = track_index + 1
                new_track = TrackInfo(title, index, length=length, index=index,
                                      medium=medium, medium_index=medium_index,
                                      medium_total=len(item["discs"])
                )
                tracks.append(new_track)

        # Format Album release date
        release_date = item["release_date"].split("-")
        year  = int(release_date[0])
        month = int(release_date[1])
        day   = int(release_date[2])


        label = None
        for lang in self.lang:
            if lang in item["publisher"]["names"]:
                label = item["publisher"]["names"][lang]

        if not label:
            label = item["publisher"]["names"].itervalues().next()

        mediums = len(item["discs"])
        media = item["media_format"]

        data_url = item["vgmdb_link"]

        return AlbumInfo(album_name, album_id,
                         artist, artist_id, tracks,
                         va=False, catalognum=catalognum,
                         year=year, month=month, day=day,
                         label=label, mediums=mediums, media=media,
                         data_source='VGMdb', data_url=data_url,
                         script='utf-8')
