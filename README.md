# Picard Lyrics

Picard Lyrics is a plugin based on [Picard Sözler](https://github.com/densizengin/picard-sozler) with various
additions (and therefore some overhead).

[lrclib](https://lrclib.net/) is used as lyrics provider or [lyricsify.com](https://www.lyricsify.com/) as a fallback.
It's free of charge, and just cool. Go check them out.

## Features

- Parse lyrics from [lrclib.net](https://lrclib.net/) or [lyricsify.com](https://www.lyricsify.com/)
- Lyrics caching, improving album load times by a lot
- Updates schedule configuration, allowing you to control when `not found`, `synced`, and `unsynced` lyrics should be
  updated
- `prefer_unsynced` setting, controlling what type of lyrics should be embedded

## Disclaimer

The plugin is **NOT** responsible for incorrectly matched lyrics and therefore accidental override of the correct ones.
It's expected from the user to check the lyrics before saving.

Some occasional mismatches or misses might happen due to the nature of
how tracks are matched against the lrclib. That project does not utilize
MusicBrainz IDs to query tracks. Instead, the names of artists, albums,
tracks, as well as the duration of the tracks are used in combination is
used to match an entry. Please see
[the lrclib API docs](https://lrclib.net/docs) for more info on the
matter. For these reasons, it is advised to skim over your lyrics.

## Installation

Download the file `picard-lyrics.py` onto your computer. Then just go to
`Options > Plugins > Install plugin...` and select the downloaded file.
The `Options` menu is on the toolbar, which is normally in the top left
corner of Picard.

After installation configuration folder should be created. You can find it in `Options > Plugins > Open Plugin Folder`,
and `Picard Lyrics` should be there.
Edit `config.json` as you need.

## Configuration

**!!!** Every update of `config.json` requires restart of the plugin

`config.json`

```json
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

```

- `*_lyrics_update_time` (nullable) - object, controlling how frequent lyrics cache should update.
  Setting it to `null` disables cache update for this specific state.
- `sources` - is a prioritized list of sources (higher - more priority). You can remove a source if you doesn't want to
  use them. If lyrics couldn't be found in higher source the program will fall back
  to the next source. Available sources for now:
    - `lrclib` - [lrclib.net](https://lrclib.net/)
    - `lyricsify` - [lyricsify.com](https://www.lyricsify.com/) (generally worse, fewer artists and fewer tracks)
- `prefer_unsynced` - controls what type of lyrics should be embedded in the metadata of a track. Synced lyrics are
  preferred by default.
- `database_path` (nullable) - allows you to control the path of `lyrics.db`. The folder with configuration file is used
  by default.

# I have an issue or feature request

Feel absolutely free to open new issue [right here](https://github.com/JustRoxy/picard-lyrics/issues)!!!

## Credits

- [irclib](https://github.com/tranxuanthang/lrclib): cool stuff
- [Picard Sözler](https://github.com/densizengin/picard-sozler): simple and just works
- [lyricsify](https://www.lyricsify.com): they definitely doesn't want applications to parse their website, but it's a
  fine resource nonetheless

## License

GNU General Public License v3.0 or later. A copy is provided in the
[LICENSE.md](./LICENSE.md) file.
