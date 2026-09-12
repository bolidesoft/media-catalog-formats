# Media catalog file formats

Format notes and small Python exporters for the databases that home movie
and book collection managers keep on disk. If you have a collection in one
of these programs and need to get the data out - to a spreadsheet, to
another program, or just to make sure it is not locked in - start here.

Everything is read-only: no tool in this repository modifies the source file.

| Program | File | Format notes | Tool | Status |
|---|---|---|---|---|
| All My Movies (Bolide) | `.amm` | [docs/allmymovies-amm.md](docs/allmymovies-amm.md) | [`tools/amm_export.py`](tools/amm_export.py) | full: movies, episodes, persons, loans, covers, shots, photos |
| All My Books (Bolide) | `.amb` | [docs/allmybooks-amb.md](docs/allmybooks-amb.md) | [`tools/amb_export.py`](tools/amb_export.py) | full: books, authors, loans, covers |
| Movienizer, Booknizer, Medianizer | `.dmo` `.dbo` `.dmb` | [docs/nizers.md](docs/nizers.md) | [`tools/nizers_export.py`](tools/nizers_export.py) | items, persons, episodes, covers |
| Kodi video library | `MyVideosNNN.db` | [docs/kodi.md](docs/kodi.md) | [`tools/kodi_export.py`](tools/kodi_export.py) | movies, TV shows, episodes, cast, ids, art URLs |
| Kodi / Emby / Jellyfin `.nfo` | `.nfo` | [docs/kodi.md](docs/kodi.md#nfo-files) | - | notes only |
| Ant Movie Catalog | `.amc` | [docs/ant-movie-catalog.md](docs/ant-movie-catalog.md) | [`tools/amc_export.py`](tools/amc_export.py) | versions 3.1-4.2, embedded pictures, custom fields, extras |
| Collectorz Book Collector | `.bkc` | [docs/collectorz.md](docs/collectorz.md) | [`tools/bkc_export.py`](tools/bkc_export.py) | schema 340 (23.x): title, authors, ISBN, plot, covers |
| Collectorz Movie Collector | `.mvc` | [docs/collectorz.md](docs/collectorz.md) | [`tools/clz_tokens.py`](tools/clz_tokens.py) | layout documented (schemas 220 and 340), token dumper; exporter wanted |
| Plex, Emby, Jellyfin | SQLite | [docs/media-servers.md](docs/media-servers.md) | - | schema notes |

## Quick start

Python 3.8 or newer. Only the two Bolide formats need a package:

```
pip install access-parser
```

```
python tools/amm_export.py "C:\Users\me\Documents\My Movies.amm" --covers
python tools/amb_export.py "My Books.amb" --covers
python tools/nizers_export.py "My movies.dmo" --covers
python tools/kodi_export.py "%APPDATA%\Kodi\userdata\Database\MyVideos131.db"
python tools/amc_export.py catalog.amc --pictures
python tools/bkc_export.py "Documents\Book Collector\MyCollection.bkc" --covers
```

Each tool writes a folder next to the source file (`<name>_export`, or
`--out`) with UTF-8 CSV files that open in Excel and LibreOffice, a JSON
file with the same data unflattened, and picture folders when asked.
Run any tool with `-h` for the options.

## Why the Bolide formats need a library

`.amm` and `.amb` are Microsoft Jet 4 databases (Access 2000 format). Two
things make them hard to read with generic tools: the pages are encrypted
with Jet's built-in "Encrypt Database" option (not a password, but the
pages are RC4-scrambled), and text columns use Jet's Unicode compression,
which most open-source readers get wrong for anything beyond Latin-1.
[`tools/jetdb.py`](tools/jetdb.py) handles both on top of the pure-Python
[`access-parser`](https://pypi.org/project/access-parser/) package, so the
files can be read on Windows, macOS and Linux without the Jet engine. On
Windows, 32-bit ADO with `Provider=Microsoft.Jet.OLEDB.4.0` works as well.

## Contributing

Corrections and additions are welcome, especially:

* a Python exporter for Movie Collector `.mvc` (layout in
  [docs/collectorz.md](docs/collectorz.md), reference implementation exists
  in Delphi);
* Collectorz lookup mapping (publisher, format, genres) for `.bkc`;
* notes on other collection managers: DVD Profiler, EMDB, CATVids, BookCAT,
  Readerware, Calibre - exports of their databases, layout notes, sample
  files you are allowed to share.

Please do not attach real collections with personal data to issues; a
cut-down sample with a few records is enough.

## About

Maintained by [Bolide Software](https://www.bolidesoft.com), the makers of
[All My Movies](https://www.bolidesoft.com/allmymovies.html) and
[All My Books](https://www.bolidesoft.com/allmybooks.html). Both programs
import every format listed above directly (with covers, cast and episodes),
and this repository documents their own database format so that your data
stays yours whatever you use next.

License: MIT.
