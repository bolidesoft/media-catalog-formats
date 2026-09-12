# Kodi video library (MyVideosNNN.db) and .nfo files

## Where the library is

Kodi keeps scraped metadata in an SQLite file in `userdata/Database/`;
the number in the name is the schema version, take the highest one:

| Kodi | file |
|---|---|
| 18 Leia | MyVideos116.db |
| 19 Matrix | MyVideos119.db |
| 20 Nexus | MyVideos121.db |
| 21 Omega | MyVideos131.db |

Paths: Windows `%APPDATA%\Kodi\userdata\`; Microsoft Store build
`%LOCALAPPDATA%\Packages\XBMCFoundation.Kodi_*\LocalCache\Roaming\Kodi\userdata\`;
portable `<install>\portable_data\userdata\`; Linux `~/.kodi/userdata/`;
profiles in `userdata\profiles\<name>\Database\`. Thumbnails are in
`userdata\Thumbnails\`, mapped by `Textures13.db` (`url -> cachedurl`).
Copy the .db file before opening it while Kodi runs.

Exporter: [`tools/kodi_export.py`](../tools/kodi_export.py).

## Tables (schema 107+, Kodi 17 and later)

Kodi uses positional columns `c00..c23` whose meaning depends on the table.

`movie`:

| col | meaning | col | meaning |
|---|---|---|---|
| c00 | title | c12 | certification ("Rated R") |
| c01 | plot | c14 | genres, `A / B / C` |
| c02 | plot outline | c15 | directors, `A / B` |
| c03 | tagline | c16 | original title |
| c05 | rating_id -> `rating` | c18 | studios |
| c06 | writers | c19 | trailer (`plugin://plugin.video.youtube/play/?video_id=ID`) |
| c07 | year (legacy; use `premiered`) | c21 | countries |
| c11 | runtime **in seconds** | c22 | path (legacy) |
| `idFile` -> `files` | | `idSet` -> `sets`, `userrating` 1..10, `premiered` date | |

`tvshow`: c00 title, c01 plot, c05 premiered, c08 genres, c09 original title,
c13 certification, c14 studio, c16 trailer; folder through `tvshowlinkpath`.
`episode`: c00 title, c01 plot, c05 aired, c12 season, c13 episode, `idShow`,
`idFile`.

Shared tables:

* `files` (strFilename, playCount, lastPlayed, dateAdded) + `path` (strPath)
  give the file name; `path.strPath` already ends with a separator.
* `actor` (actor_id, name, art_urls) with `actor_link` (role, cast_order),
  `director_link`, `writer_link`, all keyed by `media_type`
  ('movie', 'tvshow', 'episode') and `media_id`. `art_urls` is a bare URL in
  Kodi 21, `<thumb>url</thumb>` in older versions.
* `rating` (rating_type 'themoviedb'/'imdb', rating, votes) and `uniqueid`
  (type 'imdb'/'tmdb'/'tvdb', value) per media item.
* `art` (media_type, media_id, type, url): poster, fanart, thumb, clearlogo,
  banner... Skip `image://video@...` entries, those are on-the-fly video
  thumbnails. Local files appear as plain paths.
* `streamdetails` (iStreamType 0 video, 1 audio, 2 subtitle) with codec,
  width/height, duration, channels, language.
* `genre`, `country`, `studio`, `tag` with `*_link` tables; `tag` holds TMDb
  keywords (hundreds) and is usually not worth importing.
* `sets` (idSet, strSet) for collections; `seasons` for season art.

Databases before schema 107 (no `actor_link`, `rating`, `uniqueid`, `art`)
have a different layout and are not handled by the exporter.

## .nfo files

Kodi, Emby, Jellyfin, tinyMediaManager, Ember Media Manager and MediaElch
write per-movie `.nfo` files next to the video. Three shapes exist:

1. XML with root `<movie>`, `<tvshow>` or `<episodedetails>`: `title`,
   `originaltitle`, `plot`, `tagline`, `year` / `premiered` / `aired`,
   `runtime` (minutes), `mpaa`, `genre` (repeated or `A / B`), `country`,
   `studio`, `director`, `credits` (writers), `actor` (`name`, `role`,
   `thumb`), `set`, `trailer`, `playcount`, `userrating`, `rating` (old) or
   `<ratings><rating name= max=><value>` (new), ids as
   `<uniqueid type="imdb|tmdb|tvdb">`, `<imdbid>`, or `<id>`. **In new
   Kodi files `<id>` is the TMDb number**, only a value starting with `tt`
   is an IMDb id. `<thumb aspect="poster">` and `<fanart><thumb>` carry
   image URLs.
2. A "link nfo": no XML, just an IMDb or TMDb URL in the text.
3. Mixed: XML followed by a URL after the closing tag.

Encoding: honour the BOM, then the XML prolog, then assume UTF-8 if the bytes
are valid UTF-8, else the local ANSI code page (old Russian nfo files without a
prolog are Windows-1251).

## Importing

All My Movies imports the Kodi library directly (movies and TV shows with
episodes, actors with roles, technical details, IDs, posters and fanart from
the thumbnail cache) and reads `.nfo` files when adding videos from disk:
<https://www.bolidesoft.com/allmymovies.html>.
