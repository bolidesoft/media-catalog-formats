# Movienizer, Booknizer, Medianizer (Nizers) database format

| Program    | File   | Content                                               |
|------------|--------|-------------------------------------------------------|
| Movienizer | `.dmo` | movies and TV series                                  |
| Booknizer  | `.dbo` | books                                                 |
| Medianizer | `.dmb` | everything in one file, type of record in `movies.item_type` |

All three are one engine: a plain **SQLite 3** file with an identical schema.
Open it with any SQLite tool (`sqlite3`, DB Browser for SQLite, Python's
`sqlite3` module). Text is UTF-8. Nothing is encrypted; the `internal_data`
table has `password_hash` for the program's own lock, which does not affect
reading the file.

Where the file is: the program stores the location in the registry,
`HKCU\Software\Nizers\<Program>` (values `DatabasePath` and
`DatabaseFileName`); very old Movienizer used
`HKCU\Software\Movienizer\Movienizer\DatabasePath`. Covers and photos are
files in the folder `Covers` next to the database, in subfolders named after
the first letter of the file name.

Ready-made exporter: [`tools/nizers_export.py`](../tools/nizers_export.py).

## Tables that matter

```
movies          one row per item (movie / book / album / game), whatever the program name says
persons         people: actors, directors, authors, musicians
data            person <-> item links with a role (mode) and sort order
episodes        TV episodes (movie = movies.code)
editions        physical/file copies: file name, disc number, barcode, ISBN (books), pages
manuals         all lookup lists in one table, distinguished by `reference`
movies_manuals  item <-> lookup links (genres, countries, studios, tags, ...)
movies_codes    external ids and URLs: kinopoisk, imdb, trailer, kino-teatr
images          covers, shots, photos: path relative to Covers\, mode = kind
loans           loans AND the current storage location (see below)
characters      character names per actor/movie (newer schemas)
internal_data   build, schema version (60 old Booknizer, 91-92 recent), password hash
```

Schema version 92 sample column list of `movies`:
`code, title, original_title, year, description, comment, duration, imdb_code,
date_add, date_update, date_last_show, in_collection, media_type,
media_format, rating, video_standard, screen_ratio, resolution, imdb_rating,
seen, wanted, for_sale, filename, mpaa, mpaa_rating, disc_nom, salary,
custom1..custom4, checked, date_seen, filesize, video_bitrate, video_codec,
awards, disc_label, movie_number, title_sort, original_language, tomes_count,
recording_period, label, user_field1, user_filed2 (sic), series, series_nom,
tagline, year_bc, item_type`.

## Things that bite

* **Filter by `in_collection = 1 OR wanted = 1`.** The programs keep every
  record the user ever opened while browsing the online database. Real
  samples: 18 777 movie rows for a collection of 188; 343 book rows for 4
  books in the collection. Wish-list items have `in_collection = 0,
  wanted = 1`.
* **`item_type`**: 0 movies, 1 music, 2 books, 3 games. Present in Medianizer
  and in Booknizer since 2018 (schema 92); absent in old Booknizer files
  (schema 60). Check `pragma table_info(movies)`, not the file extension.
* **Roles in `data.mode`** are numbered the movie way even in book files.
  Movies: 1 director, 2 writer, 3 actor, 4 character, 5 producer, 6 composer.
  Books: 3 author; old Booknizer also used 1 editors, 4 translators.
  The `modes` table always says Directors/Writers/Actors/Characters.
* **Lookup lists** are all in `manuals`, selected by `reference`, linked
  through `movies_manuals (movie, reference, ref_code)`. Observed values:

  | reference | list                                   | reference | list                    |
  |-----------|----------------------------------------|-----------|-------------------------|
  | 1  | video standard (NTSC, PAL)                    | 11 | age rating (MPAA)             |
  | 2  | media format (DVD, Blu-ray; books: PDF, EPUB) | 12 | studio (books: publisher)     |
  | 3  | media type (Movie, Television, Animation)     | 13 | custom                        |
  | 4  | aspect ratio                                  | 17 | user tags                     |
  | 5  | resolution (books: dimensions)                | 19 | video codec                   |
  | 6  | language                                      | 20 | disc label                    |
  | 7  | audio track ("Russian AC3 6 ch")              | 21 | edition                       |
  | 8  | genre                                         | 22 | series                        |
  | 9  | country (old books: city)                     | 23 | subtitles                     |
  | 10 | storage location                              | 30 | instrument (music)            |

  Scalar columns `media_format`, `media_type`, `resolution`,
  `screen_ratio`, `mpaa`, `disc_label`, `series` in `movies` hold codes into
  the same table.
* **Storage location is not in `movies`.** Movienizer records it in `loans`:
  the open row (empty `return_date`) with `location` pointing to a
  `manuals` row of `reference = 10`. Closed rows are the loan history.
* **`movies.disc_nom` is declared INTEGER but holds text** ("П-19"). SQLite
  does not care, but typed wrappers do: read it with `CAST(disc_nom AS TEXT)`.
  `editions.disc_nom` is VARCHAR and is filled more often.
* **Ratings**: `movies.rating` is the user's 1..10; `imdb_rating` is REAL
  (6.5); `movies_codes.rating` holds the source rating (Kinopoisk).
* **Dates** are text `YYYY-MM-DD HH:MM:SS`; `loans.loan_date` is `MM/DD/YYYY`.
* **Images**: `images.mode` 1 front cover, 2 back cover, 3 shot, 4 poster,
  5 user image, 6 person photo, 7 backdrop, 8 trailer, 9 season cover,
  10 episode cover, 11 CD scan. `path` is relative to `Covers\`
  (`Ф\Фактотум-02.jpg`), `url` is where it was downloaded from. The
  `images_modes` table lists these names; its third column is a sort order,
  not the mode number.
* **Books**: ISBN lives in `editions.features` (several separated by `<br>`),
  page count in `editions.duration`, print run in `editions.circulation`,
  publisher through `reference = 12`.
* **Series**: `episodes` has `movie, season, episode, title, original_title,
  original_air_date, description, seen, rating`.

## Example queries

Collection with genres and director:

```sql
SELECT m.code, m.title, m.original_title, m.year,
       (SELECT group_concat(man.name, ', ') FROM movies_manuals mm
          JOIN manuals man ON man.code = mm.ref_code AND man.reference = mm.reference
         WHERE mm.movie = m.code AND mm.reference = 8) AS genres,
       (SELECT group_concat(p.name, ', ') FROM data d JOIN persons p ON p.code = d.person
         WHERE d.movie = m.code AND d.mode = 1) AS directors,
       (SELECT path FROM images i WHERE i.movie = m.code AND i.mode = 1
         ORDER BY sort_order, code LIMIT 1) AS cover
FROM movies m
WHERE (m.in_collection = 1 OR m.wanted = 1) AND COALESCE(m.item_type, 0) = 0
ORDER BY m.title;
```

Actors with character names:

```sql
SELECT p.name, c.name AS character
FROM data d JOIN persons p ON p.code = d.person
LEFT JOIN characters c ON c.movie = d.movie AND c.person = d.person
WHERE d.movie = ? AND d.mode = 3
ORDER BY d.sort_order;
```

## Importing into something else

All My Movies (movies, series with episodes, persons with photos, covers,
shots, locations, tags, Kinopoisk/IMDb links) and All My Books (Booknizer and
the book part of Medianizer) import these files directly, including the
`Covers` folder: <https://www.bolidesoft.com/allmymovies.html>,
<https://www.bolidesoft.com/allmybooks.html>.
