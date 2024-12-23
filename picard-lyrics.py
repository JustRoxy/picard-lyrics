# Picard Lyrics is a plugin that fetches lyrics from a multiple public APIs.
# Copyright (C) 2024 JustRoxy <JustRoxyOsu@inbox.ru>
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.
import enum
import json
import os.path
import re
from datetime import timedelta, datetime

import picard.track
from picard.webservice import WebService, USER_AGENT_STRING

PLUGIN_NAME = "Picard Lyrics"
PLUGIN_AUTHOR = "JustRoxy <JustRoxyOsu@inbox.ru>"
PLUGIN_DESCRIPTION = "Fork of /Sözler is a lyrics fetcher for Picard. It uses the public API provided by the lrclib.net project, which requires no registration or API keys! The API provides synced lyrics and unsynced ones as a fallback. We prioritize the syced ones. The lrclib project does not utilize MB IDs, so the results may not be as accurate. It is recommended to glimpse over your lyrics when tagging./"
PLUGIN_VERSION = "0.0.2"
PLUGIN_API_VERSIONS = ["2.1"]
PLUGIN_LICENSE = "GPL-3.0-or-later"
PLUGIN_LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0-standalone.html"

from functools import partial
import sqlite3

from picard.metadata import register_track_metadata_processor
from picard import log

DEFAULT_DIRECTORY_PATH = os.path.join(os.path.dirname(__file__), PLUGIN_NAME)
DEFAULT_CONFIG_PATH = os.path.join(DEFAULT_DIRECTORY_PATH, "config.json")
DEFAULT_DATABASE_FILE_PATH = os.path.join(DEFAULT_DIRECTORY_PATH, "lyrics.db")


def log_debug(s):
    log.debug(f"{PLUGIN_NAME}: {s}")


def log_info(s):
    log.info(f"{PLUGIN_NAME}: {s}")


def log_warn(s):
    log.warning(f"{PLUGIN_NAME}: {s}")


def log_err(s):
    log.error(f"{PLUGIN_NAME}: {s}")


class LyricsState(enum.IntEnum):
    NOT_FOUND = 0,
    INSTRUMENTAL = 1,
    SYNCED = 2,
    UNSYNCED = 3


class LyricsSource(enum.IntEnum):
    UNKNOWN = 0,
    LRCLIB = 1,
    Lyricsify = 2


class Lyrics:
    def __init__(self, track_id, lyrics, state, last_updated, source):
        self.track_id = track_id
        self.lyrics = lyrics
        self.state = state
        self.last_updated = last_updated
        self.source = source

    @staticmethod
    def create_from_tuple(lyrics_tuple: tuple):
        return Lyrics(lyrics_tuple[0], lyrics_tuple[1], LyricsState(lyrics_tuple[2]),
                      datetime.fromtimestamp(lyrics_tuple[3]),
                      LyricsSource(lyrics_tuple[4]))

    @staticmethod
    def create_empty_lyrics(track_id):
        return Lyrics(track_id, None, LyricsState.NOT_FOUND, datetime.min, LyricsSource.UNKNOWN)

    def to_tuple(self) -> tuple:
        return self.track_id, self.lyrics, self.state, datetime.timestamp(self.last_updated), self.source


class Config:
    @staticmethod
    def parse_update_time(config_dict, key) -> timedelta | None:
        if config_dict[key]:
            update_time = config_dict[key]
            return timedelta(update_time["days"], 0, 0, 0, update_time["minutes"], update_time["hours"])

        return None

    @staticmethod
    def __create_directory_if_not_exist():
        if not os.path.exists(DEFAULT_DIRECTORY_PATH):
            os.mkdir(DEFAULT_DIRECTORY_PATH)

    @staticmethod
    def read_config_file():
        Config.__create_directory_if_not_exist()

        if not os.path.exists(DEFAULT_CONFIG_PATH):
            # create default config if it doesn't exist
            with open(DEFAULT_CONFIG_PATH, 'w') as f:
                f.write(Config.default_config_json())

            log_info(f'created configuration file at path={DEFAULT_CONFIG_PATH}')

        with open(DEFAULT_CONFIG_PATH, 'r') as f:
            return Config(json.load(f))

    @staticmethod
    def default_config_json() -> str:
        # Replace { "days"... "hours"... } with null to disable updates completely and vice versa

        return """
{
  "not_found_lyrics_update_time": {
    "days": 1,
    "hours": 0,
    "minutes": 0,
    "seconds": 0
  },
  "synced_lyrics_update_time": {
    "days": 30,
    "hours": 0,
    "minutes": 0,
    "seconds": 0
  },
  "unsynced_lyrics_update_time": null,
  "sources": [
    "lrclib",
    "lyricsify"
  ],
  "prefer_unsynced": false,
  "database_path": null
}
        """

    def __init__(self, config_dict):
        try:
            self.not_found_lyrics_update_time = Config.parse_update_time(config_dict, "not_found_lyrics_update_time")
            self.synced_lyrics_update_time = Config.parse_update_time(config_dict, "synced_lyrics_update_time")
            self.unsynced_lyrics_update_time = Config.parse_update_time(config_dict, "unsynced_lyrics_update_time")
            self.sources: [str] = config_dict["sources"]
            self.prefer_unsynced = config_dict["prefer_unsynced"]
            self.database_path = config_dict["database_path"] or DEFAULT_DATABASE_FILE_PATH
        except Exception as e:
            raise Exception(
                "Failed to parse config file, please verify that it's correct. Refer to `default_config.json` in the repository for an example") from e  # throwing exception (in contrast of fall-backing) is valid because malformed config can only occur due to manual change


config = Config.read_config_file()


def initialize_database():
    log_debug(f"initializing connection to sqlite database on path={config.database_path}")
    initialize_database_connection = sqlite3.connect(config.database_path)
    initialize_database_cursor = initialize_database_connection.cursor()
    initialize_database_cursor.execute("""
    CREATE TABLE IF NOT EXISTS lyrics (
        track_id text PRIMARY KEY,
        lyrics text,
        status int, -- see `LyricsStatus` for statuses
        last_updated int,
        source int -- see `LyricsSource` for sources
    )
    """)

    return initialize_database_cursor, initialize_database_connection


(cursor, db_connection) = initialize_database()


def database_query_lyrics(track_id: str) -> Lyrics | None:
    lyrics_tuple = cursor.execute("SELECT * FROM lyrics WHERE track_id = (?)", (track_id,)).fetchone()
    if lyrics_tuple is None:
        return None

    return Lyrics.create_from_tuple(lyrics_tuple)


def database_upsert_lyrics(lyrics: Lyrics) -> None:
    lyrics.last_updated = datetime.now()

    cursor.execute("""
    INSERT INTO lyrics(track_id, lyrics, status, last_updated, source) VALUES (?, ?, ?, ?, ?) ON CONFLICT(track_id) DO UPDATE SET 
        lyrics = excluded.lyrics, 
        status = excluded.status,
        last_updated = excluded.last_updated,
        source = excluded.source
    """, lyrics.to_tuple())

    db_connection.commit()


def process_response(chain, track_id, album, metadata, data, reply, error):
    handler = chain[0]

    album._requests -= 1

    try:
        if handler.not_found(data, error):
            log.debug(f"({handler}) haven't found track_id={track_id}, skipping to the next handler")
            handle_next_handler_in_chain(chain[1:], track_id, album, metadata)
            return
    except Exception as e:
        log_err(
            f"({handler}) got error on the error handling, skipping to the next handler. exception = {e}")

        handle_next_handler_in_chain(chain[1:], track_id, album, metadata)
        return

    try:
        processed_lyrics = handler.process_response(track_id, data)
        if not assert_correct_processed_lyrics(processed_lyrics):
            log_err(f"({handler}) got error on the assertion, skipping to the next handler")
            handle_next_handler_in_chain(chain[1:], track_id, album, metadata)
            return

        metadata["lyrics"] = processed_lyrics.lyrics
        database_upsert_lyrics(processed_lyrics)
    except Exception as e:
        log_err(f"({handler}) got error on lyrics processing, skipping to the next handler. exception = {e}")
        handle_next_handler_in_chain(chain[1:], track_id, album, metadata)
        return

    album._finalize_loading(None)


def assert_correct_processed_lyrics(lyrics: Lyrics) -> bool:
    if not (lyrics.source != 0):
        log_err(f"expected source of processed_lyrics not to be 0, found: {lyrics.source}")
        return False

    return True


class LrcLib:
    def __str__(self):
        return "LrcLib"

    # todo: (bottleneck) change to metadata parameter if needed
    def create_request(self, artist_name, album_name, track_name, length):
        try:
            (mins, secs) = map(int, length.split(":"))
        except Exception as e:
            log.warning(f"failed to get the length of the track {track_name} by {artist_name}, skipping lrclib...")
            return None

        query = {
            "artist_name": artist_name,
            "album_name": album_name,
            "track_name": track_name,
            "duration": mins * 60 + secs,  # accepts seconds only
        }

        return {
            "url": "https://lrclib.net/api/get",
            "queryargs": query
        }

    def not_found(self, response, error) -> bool:
        # QNetworkReply::ContentNotFoundError(203)-the remote content was not found at the server (similar to HTTP error 404)
        if error == 203:
            return True

        return False

    def process_response(self, track_id, response) -> Lyrics:
        data = json.loads(response)

        # resolve track_id later
        lyrics = Lyrics.create_empty_lyrics(track_id)
        lyrics.source = LyricsSource.LRCLIB

        if data.get("instrumental"):
            log_debug("instrumental track; skipping")
            (lyrics.lyrics, lyrics.state) = (None, LyricsState.INSTRUMENTAL)
            return lyrics

        if config.prefer_unsynced:
            (lyrics.lyrics, lyrics.state) = (data.get("plainLyrics"), LyricsState.UNSYNCED) or (
                data.get("syncedLyrics"), LyricsState.SYNCED)
        else:
            (lyrics.lyrics, lyrics.state) = (data.get("syncedLyrics"), LyricsState.SYNCED) or (
                data.get("plainLyrics"), LyricsState.UNSYNCED)

        return lyrics


class Lyricsify:
    def __init__(self):
        self.ORIGINAL_USER_AGENT = picard.webservice.USER_AGENT_STRING
        self.content_regex = re.compile(r"lrcText = \"(.+)\";\$", re.MULTILINE)
        self.metatags_regex = re.compile(r"\[[a-zA-Z]+:.*\]\n", re.MULTILINE)
        self.sync_content = re.compile(r"\[\d+", re.MULTILINE)

    def __str__(self):
        return "Lyricsify"

    # todo: (bottleneck) change to metadata parameter if needed
    def create_request(self, artist_name: str, album_name: str, track_name: str, _):
        folder = artist_name.lower().replace(" ", "-")
        file = track_name.lower().replace(" ", "-")

        # warn: we NEED to replace User-Agent for this request, and probably it's going to break something
        picard.webservice.USER_AGENT_STRING = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        return {
            "url": f"https://www.lyricsify.com/lyrics/{folder}/{file}",
        }

    def not_found(self, response, error) -> bool:
        # return back User-Agent :D
        picard.webservice.USER_AGENT_STRING = self.ORIGINAL_USER_AGENT

        return self.content_regex.search(response.decode('utf-8')) is None

    # \nlrcText = "[id: iltctltz]\\n[ar: Aphex Twin]\\n[al: Richard D. James Album]\\n[ti: 4]\\n[length: 04:40]\\n[01:33.01]Richard\\n[01:33.95]Yeah?\\n[03:06.54]Richard\\n[03:07.28]Yeah?\\n[03:11.75]"
    def process_response(self, track_id, response) -> Lyrics:
        # resolve track_id later
        lyrics = Lyrics.create_empty_lyrics(track_id)
        lyrics.source = LyricsSource.Lyricsify

        lyrics_content = self.content_regex.search(response.decode('utf-8')).group(1).replace('\\n', '\n')
        lyrics_content = self.metatags_regex.sub('', lyrics_content)  # remove metatags from the lyrics

        if self.sync_content.match(lyrics_content) is None:
            lyrics.state = LyricsState.UNSYNCED
        else:
            lyrics.state = LyricsState.SYNCED

        lyrics.lyrics = lyrics_content

        return lyrics


def check_update_time(now: datetime, last_updated: datetime, should_update_in: timedelta | None) -> bool:
    if should_update_in is None:
        return False

    return (now - last_updated) > should_update_in


def should_update_lyrics(lyrics_entity: Lyrics | None):
    if lyrics_entity is None:
        log_debug("lyrics doesn't exist and should be updated")
        return True

    now = datetime.now()
    if lyrics_entity.state == LyricsState.NOT_FOUND:
        log_debug(f"checking update time for NOT_FOUND. track_id={lyrics_entity.track_id}")
        return check_update_time(now, lyrics_entity.last_updated, config.not_found_lyrics_update_time)

    if lyrics_entity.state == LyricsState.SYNCED:
        log_debug(f"checking update time for SYNCED. track_id={lyrics_entity.track_id}")
        return check_update_time(now, lyrics_entity.last_updated, config.synced_lyrics_update_time)

    if lyrics_entity.state == LyricsState.UNSYNCED:
        log_debug(f"checking update time for UNSYNCED. track_id={lyrics_entity.track_id}")
        return check_update_time(now, lyrics_entity.last_updated, config.unsynced_lyrics_update_time)

    if lyrics_entity.state == LyricsState.INSTRUMENTAL:  # todo: right now we always skip instrumental tracks
        log_debug(f"INSTRUMENTAL tracks are skipped. track_id={lyrics_entity.track_id}")
        return False


# list of (create_request, not_found, response -> Lyrics map)


def build_source_chain():
    if not config.sources or len(config.sources) == 0:
        log_warn("unable to find source priority list, falling back to default")
        return [LrcLib(), Lyricsify()]

    commands = []
    for source in config.sources:
        match source.lower():
            case "lrclib":
                commands.append(LrcLib())
            case "lyricsify":
                commands.append(Lyricsify())
            case x:
                raise Exception(f"Unknown lyrics source: {x}. Check the default configuration for available sources")
    return commands


CHAIN_OF_COMMANDS = build_source_chain()


def default_not_found(track_id):
    return Lyrics.create_empty_lyrics(track_id)


def handle_next_handler_in_chain(chain, track_id, album, metadata):
    artist_name = metadata["albumartist"] or metadata["artist"]
    album_name = metadata["album"]
    track_name = metadata["title"]
    length = metadata["~length"]

    if len(chain) == 0:
        log.debug(f"empty chain, lyrics not found for track_id={track_id}")
        not_found_lyrics = default_not_found(track_id)
        database_upsert_lyrics(not_found_lyrics)
        album._finalize_loading(None)
        return

    handler = chain[0]

    log_debug(
        f"({handler}) processing track track_id={track_id}, artist_name={artist_name}, album_name={album_name}, track_name={track_name}")

    request = handler.create_request(artist_name, album_name, track_name, length)
    if request is None:
        log_warn(f"({handler}) unable to create the query, skipping...")
        handle_next_handler_in_chain(chain[1:], track_id, album, metadata)
        return

    log_debug(f"trying to request with: {request}")

    request["handler"] = partial(process_response, chain, track_id, album, metadata)
    album.tagger.webservice.download_url(**request)

    album._requests += 1


def process_track(album, metadata, track, __):
    track_id = metadata["musicbrainz_recordingid"]

    lyrics = database_query_lyrics(track_id)
    if not should_update_lyrics(lyrics):
        log_debug(f"skipping track {track_id}, doesn't require update")
        metadata["lyrics"] = lyrics.lyrics
        return

    handle_next_handler_in_chain(CHAIN_OF_COMMANDS, track_id, album, metadata)


register_track_metadata_processor(process_track)
