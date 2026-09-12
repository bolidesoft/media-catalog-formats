# All My Movies database format (*.amm)

An `.amm` file is a **Microsoft Jet 4** database (the engine behind Access
2000-2003 `.mdb` files) with a fixed set of tables. It can be opened with
Access, with ADO/OLE DB (`Provider=Microsoft.Jet.OLEDB.4.0`, 32-bit only) or,
without Windows, with the pure-Python reader in this repository:
[`tools/jetdb.py`](../tools/jetdb.py) and the exporter
[`tools/amm_export.py`](../tools/amm_export.py).

Two format details are easy to miss:

1. **Page encryption.** Databases created by the program use Jet's
   "Encrypt Database" option. This is not a password: every page except the
   header is RC4-encrypted with a 32-bit key kept in the header at offset
   0x3E (XOR-masked with `FB 8A BC 4E`). Jet handles it transparently;
   `mdbtools`, `access_parser` and similar libraries need the pages
   decrypted first (`jetdb.py` does that in memory).
2. **Compressed Unicode text.** All `TEXT` columns are `WITH COMP`: Jet
   stores them as UCS-2 with a marker `FF FE` and runs of single bytes for
   U+0000..U+00FF, switching to two-byte UTF-16LE after a `00` toggle byte.
   Libraries that ignore the toggle mangle Cyrillic, Greek, CJK text.

A database can also carry a Jet database password (menu *Database / Password*);
then the file cannot be opened by third-party tools at all without it. The
more common *write password* (`WritePass` in the settings blob) only stops
editing inside the program and does not affect reading.

## Files around the database

```
My Movies.amm             the database
My Movies_images2\NN\     pictures when "store images inside the database" is OFF
My Movies_thumbs2\NN\     cached thumbnails (rebuildable, safe to ignore)
```

`NN` is `id mod 100` as two digits. File names are `m<images.ID>.jpg` for
movie covers and shots, `a<ActorImages.ID>.jpg` for person photos,
`f<FriendImages.ID>.jpg` for friend photos; thumbnails are `<MovieID>.jpg`.
Whether pictures are inside the file or outside is recorded per database in
the settings blob (`[main] ImagesInside`); in practice check both places -
a picture is either a non-empty `image` blob or an existing file.

## Tables

```
movies          the film records (see columns below)
Actors          persons: actors, directors, writers (one table for all roles)
ActorsLink      movie <-> actor with Role text and Sorter
DirectorLink    movie <-> director (ActorID), Sorter
ScenarioLink    movie <-> writer (ActorID), Sorter
Genres / GenresLink, Countries / CountryLink
MediaType, MediaLocation, QualityValues     lookups referenced from movies
images          covers and shots: MovieID, cover (bit), Sorter, hint, image (blob)
ActorImages     person photos: ActorID, Sorter, image
ActorImageTags  which persons are on a movie shot
Episodes        TV episodes: MovieID, SeasonNum, EpisodeNum, EpisodeTitle, AirDate, Description, seen, rating, mydate, localpath
friends, FriendImages, LoanHistory (MovieID, FriendID, Loan, Overdue, return)
CustomFields / CustomFieldsLink (Value text), CustomFlags / CustomFlagsLink (Value bit)
FileLinks       extra files attached to a movie (Title, Filename)
settings        one blob per profile with database-level options
```

### `movies`

| column | meaning |
|---|---|
| `MovieID` | primary key (autoincrement) |
| `movienum` | the number shown in the list; user-editable |
| `Name`, `originaltitle` | title and original title |
| `year` | text, 4 chars |
| `length` | minutes, text |
| `rating` | online rating x10 (86 = 8.6), byte |
| `myrating` | user rating x10 |
| `seen`, `wishlist`, `hidden` | bits |
| `description`, `comments` | memo |
| `mpaa`, `studio`, `url`, `Trailer`, `barcode` | text |
| `mediatypeID`, `medialocationID`, `qualityID` | lookups (-1 = none) |
| `medialabel`, `mediacount` | disc label and number of discs |
| `LocalPath` | main video file |
| `size`, `resolution`, `aspectratio`, `subtitles` | text |
| `videoinfo` | `codec~frame rate~bit depth~bitrate~stream count` |
| `audioinfo` | see below |
| `adddate`, `Modified` | date/time |
| `loan`, `LoanFriendID`, `returndate` | current loan (empty when at home) |
| `BorrowFriendID` | the movie is borrowed from that friend |
| `Price` | single |
| `CoverWidth`, `CoverHeight` | cached cover size |

`audioinfo` exists in three layouts, oldest first; new records are always JSON:

```
codec~bitrate~info
codec1,codec2~bitrate1,bitrate2~lang1,lang2
{"i":[{"l":"English","c":"DTS-HD Master Audio","b":"3 200 kb/s","h":"6","s":"48.0 kHz"}]}
```

### `Actors`

`ActorID, Name, AltName, BirthDay (text, "12 November"), BirthYear,
DeathYear, BirthPlace, CountryID, URL, Rating, biography, filmography,
Comments`; `reserved1..3` are internal.

### The `settings` blob

Row `Profile = 'default'`, column `Data`: a sequence of records
`80-byte header + payload`. Header: `int32 0x112`, `char[36] section`,
`char[36] key`, `int32 size`. Both header and payload are XOR-ed with the key
`hDmpSwrdGZxqlHdgfcIRuHsDHs5Tu`, starting at key index -1, so the first byte
of every block is stored as is. Values are untyped: 1 byte = boolean, 4 bytes
= int32, otherwise a string (UTF-8 when `[meta] strenc >= 2`, else ANSI).
Keys worth knowing: `[main] ImagesInside`, `[main] WritePass`.
Implementation: `parse_settings_blob` in
[`tools/bolide_common.py`](../tools/bolide_common.py).

## Reading it yourself

Windows, any language with ADO (32-bit process):

```
Provider=Microsoft.Jet.OLEDB.4.0;Data Source=C:\path\My Movies.amm
SELECT m.MovieID, m.Name, m.year, g.Name AS genre
FROM (movies m LEFT JOIN GenresLink gl ON gl.MovieID = m.MovieID)
     LEFT JOIN Genres g ON g.GenreID = gl.GenreID
```

Anywhere, Python:

```python
from jetdb import JetDatabase        # tools/jetdb.py, needs: pip install access-parser
db = JetDatabase("My Movies.amm")
for m in db.rows("movies"):
    print(m["Name"], m["year"], m["rating"] / 10)
```

`tools/amm_export.py` writes CSV/JSON for movies, episodes, persons, friends
and loans, and extracts covers, shots and photos from either storage.

Product page: <https://www.bolidesoft.com/allmymovies.html>.
