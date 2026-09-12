# Plex, Emby and Jellyfin libraries

All three servers keep the scraped library in SQLite. The files are open
(no encryption), but each server has its own schema, and Jellyfin changed
its schema completely in 10.11. All My Movies imports all of them directly;
these notes are what that importer relies on.

## Plex Media Server

File: `Plug-in Support\Databases\com.plexapp.plugins.library.db`
(with `-wal` and `-shm` next to it: copy all three). Data folder on Windows
`%LOCALAPPDATA%\Plex Media Server` unless `LocalAppDataPath` is overridden
in `HKCU\Software\Plex, Inc.\Plex Media Server`.

* `metadata_items`: `metadata_type` 1 movie, 2 show, 3 season, 4 episode
  (12 = trailers/extras, `library_section_id` NULL); `parent_id`, `index`
  (season/episode number), `title`, `original_title`, `year`,
  `originally_available_at` (midnight UTC - do not shift to local time),
  `summary`, `tagline`, `duration` in ms, `rating`, `audience_rating`
  (0..10), `content_rating` ("ru/16+"), `studio`, `user_thumb_url`,
  `user_art_url`, `added_at` (unix).
* `media_items` -> `media_parts` (`file`) -> `media_streams`
  (`stream_type` 1 video, 2 audio, 3 subtitle).
* `tags` + `taggings`: `tag_type` 1 genre, 2 collection, 4 director,
  5 writer, 6 actor (`taggings.text` = character), 7 producer, 8 country,
  10 review, 314 external ids (`imdb://tt...`, `tmdb://`, `tvdb://`),
  316 source ratings (`imdb://image.rating`, text = value), 318 studios,
  319 network.
* `metadata_item_settings` (`guid`, `view_count`, `rating`) - watched
  state and user rating.
* Some indexes use the `icu_root` collation; a SQLite client without ICU
  must register a dummy collation or queries fail with "no such collation".
* Image URLs: `metadata://posters/<sha1>` -> `Metadata\Movies\<h[0]>\<h[1:]>.bundle\Contents\_combined\posters\<sha1>` (no extension);
  `media://...` -> `Media\localhost\...`;
  `https://images.plex.tv/photo?...&url=<original>` - the original URL can be fetched directly.
  The local HTTP API needs `X-Plex-Token`, which exists only for a claimed server.

## Emby Server 4.x

File: `programdata\data\library.db` (`%APPDATA%\Emby-Server\programdata\data`
on Windows).

* `MediaItems`: `type` 5 movie, 6 series, 7 season, 8 episode, 21 genre,
  23 person, 29 studio, 34 tag; fields `Name`, `OriginalTitle`, `Overview`,
  `ProductionYear`, `PremiereDate`, `RunTimeTicks`, `OfficialRating`,
  `CommunityRating`, `Path`, `ParentId`, `IndexNumber`,
  `ParentIndexNumber`, `Images` (text: `path*date*type*w*h*blurhash|...`),
  `ProviderIds` (`Imdb=tt...|Tmdb=...`), dates as unix seconds.
* `ItemLinks2` (`Type` 2 genre, 3 studio) -> `MediaItems.Name`;
  `ItemPeople2` (`PersonType` 0 actor, 1 director, 2 writer, `Role`);
  `MediaStreams2` (`StreamType` 1 audio, 2 video, 3 subtitle);
  `UserDatas` by `UserDataKeyId` (Played, PlayCount, Rating, IsFavorite);
  `ImportedCollections`, `RemoteTrailers`.

## Jellyfin

* **10.11 and later**: `data\jellyfin.db` (EF Core). `BaseItems` with text
  GUID `Id` and `Type` = full .NET class name
  (`MediaBrowser.Controller.Entities.Movies.Movie`, `...TV.Series`,
  `...TV.Season`, `...TV.Episode`); `PeopleBaseItemMap` + `Peoples`
  (`Role` = character for actors, "Director"/"Writer" for the others);
  `BaseItemProviders` (Imdb, Tmdb, Tvdb); `BaseItemImageInfos` (`ImageType`
  0 primary/poster, 2 backdrop; file paths); `MediaStreamInfos`
  (`StreamType` 0 audio, 1 video, 2 subtitle); `UserData` (Played, Rating,
  Likes, IsFavorite).
* **10.10 and earlier** (and Emby 3.x): `data\library.db`, table
  `TypedBaseItems` with a BLOB `guid` (compare with `hex()`), `People`,
  `UserDatas` (key = `UserDataKey`), `mediastreams` (`StreamType` as words),
  `Images` and `ProviderIds` as text in the same layout as Emby above.
* Data folder: service install `C:\ProgramData\Jellyfin\Server\data`,
  tray app `%LOCALAPPDATA%\jellyfin\data`, or `JELLYFIN_DATA_DIR`.

Both Emby and Jellyfin also read Kodi `.nfo` files from the media folders,
so a library can often be rebuilt from the `.nfo` files alone
([kodi.md](kodi.md)).

## Importing

All My Movies imports Plex, Emby and Jellyfin libraries (movies, series with
episodes, cast with roles, external ids, posters and backdrops, watched
state and ratings): <https://www.bolidesoft.com/allmymovies.html>.
