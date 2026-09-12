# Collectorz.com desktop databases (Book Collector *.bkc, Movie Collector *.mvc)

Collectorz.com discontinued the Windows/macOS "Collector" desktop programs in
favour of the CLZ subscription apps. The desktop databases (`.bkc` books,
`.mvc` movies; music, game and comic collectors use the same container) are
**not** a database engine file: they are a Delphi `TWriter`-style stream of
tagged values, written positionally and without field names. Reading them
means knowing the record layout of the version that wrote the file.

Tools: [`tools/clz_tokens.py`](../tools/clz_tokens.py) dumps the token stream
of any of these files; [`tools/bkc_export.py`](../tools/bkc_export.py)
extracts books from a `.bkc` of schema 340 (Book Collector 23.x). A Python
reader for `.mvc` is not written yet; the layout of two `.mvc` schemas is
described below and is implemented in Delphi in All My Movies.

Where the files are: `Documents\Book Collector\*.bkc`,
`Documents\Movie Collector\*.mvc` (older versions: `Public Documents\`).
A `<name>.bkclck` / `.mvclck` lock file (XML with the PC and user name)
sits next to the database while it is open and survives a crash. Backups
are in a `Backup` subfolder. Cover files are in `Images\` next to the
database; the database stores absolute paths from the original machine, so
match by file name.

## Tags

| tag | value |
|---|---|
| `00` | end of list / null |
| `01` | start of list (nesting allowed) |
| `02` `03` `04` | int8 / int16 / int32, little-endian, **signed** (`02 FF` is -1, the usual "no reference") |
| `05` | 10-byte x87 extended float (prices; -1.0 = not set) |
| `06` | ANSI string: 1 byte length + bytes (used only in the file header) |
| `08` / `09` | False / True |
| `11` | 8-byte double = Delphi TDateTime (days since 1899-12-30) |

**Unicode strings have no tag of their own.** A string is a tagged integer
(the length in characters) followed by that many UTF-16LE code units; an
empty string is therefore indistinguishable from the integer 0, and any
integer could be the start of a string. `clz_tokens.py` decides by checking
whether the following `len*2` bytes look like text, which is right in all
but a handful of places (pairs of adjacent small integers).

## Header

```
06 0E "Collectorz.com"
06 04 "Book"  |  06 05 "Movie"
03 xx xx        int16 schema version: 220 = Movie Collector 9.x (2013), 340 = 23.x (last)
03 xx xx        int16 application version (2301 = 23.0.1)
...             GUID of the collection, file name, "CLZ-0000" (schema 340)
```

Then the lookup lists come as nested `01 ... 00` lists in a fixed order
(years, genres, formats, publishers/studios, countries, languages, stores,
owners, locations, tags, extras, subjects, **persons**, conditions ...).
Each entry starts `INT id, 0, 0, 0, TRUE, 0, STR name` (schema 340) or
`INT id, 0, 0, STR name` (schema 220). Ids are global across the file and
records refer to them by number.

## Book record, schema 340

```
INT16 id, INT8 ordinal, STR "{GUID}"          <- anchor
... small ints and flags, DATE added
STR  cover path         (absolute, ...\Book Collector\Images\<x>.jpg)
LIST links (name, URL, type)
EXT  price, EXT -1, EXT -1
INT32 flags
STR  ISBN-13
STR  thumbnail path     (...\Thumbnails\<md5>.png)
INT16, 0, 0, 0, TRUE, 0
STR  title, 0, 0, STR subtitle (or 0), STR plot (or 0)
...
LIST credits: INT creditId, 0, 0, 0, TRUE, 0, INT role, INT personId, INT -1
             (role 12 = author; personId -> persons lookup)
```

`bkc_export.py` locates fields by these anchors and validates types, so on
an unknown version fields come out empty rather than shifted.

## Movie record, schema 220 (Movie Collector 9.x)

Anchor `INT id, INT ordinal (< id), 0, STR title`; then `+1` sort title,
`+3` edition ("Platinum Edition"), `+5` front cover, `+6` back cover,
`+7` plot, `+8` IMDb number, `+9` list of links. Counting from the end of
the link list (L): `L+1` minutes, `L+16` price, `L+22` year (id in the years
lookup), `L+25` country, `L+26` language, `L+27` media format, `L+34` age
rating; then eight lists in order: genres, studios, video format, crew
(`[id, 0, 0, role, person]`: 8 director, 49 writer, 7 producer), actors
(same plus character string), subtitles, regions, audio tracks; then the
IMDb rating string ("6.8"), the added date and the list of discs.

## Movie record, schema 340 (Movie Collector 23.x)

Anchor `INT id, INT ordinal, STR "{GUID}"`, then `0, TRUE, 0, STR title,
STR sort title`. Cover, plot and IMDb URL sit right before the first list
(the links list) at -4, -2, -1. From the end of the links list: `L+1`
minutes, `L+16` price, `L+17` location, `L+22` year (id), `L+25` country,
`L+26` language, `L+27` a **list** of media formats; the age rating is the
7th token after that list and the block of lists (genres, studios, crew,
actors) starts at the 8th. Credit entries are
`[id, 0, 0, 0, TRUE, 0, role, person, ordinal, (character | 0)]`, role 51 =
composer. Then the series reference, IMDb rating string, added date,
thumbnail, vote count and the disc list; **TV episodes are inside the disc
records** as the second nested list: `[title, description, minutes,
year(id), month, day, two lists, flags, still URL ...]` - season and
episode numbers are not stored and can only be taken from the still URL
(`..._Futurama_1_2.jpg`). Back cover (`_p.jpg`) and stills (`_d.jpg`) are
at the end of the record.

## Importing

All My Movies reads `.mvc` of both schemas directly (with episodes, cast,
covers from `Images\`) and All My Books reads `.bkc`; both also import the
XML export of the Collector programs: <https://www.bolidesoft.com/allmymovies.html>,
<https://www.bolidesoft.com/allmybooks.html>.
