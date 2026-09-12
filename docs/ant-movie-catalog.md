# Ant Movie Catalog binary catalog (*.amc)

Ant Movie Catalog (AMC, <https://www.antp.be/software/moviecatalog>, GPL)
saves catalogs either as XML (`.xml`, self-describing) or in its own binary
format `.amc`. The binary format is a straight serialization of the program's
records: little-endian `int32` numbers, 1-byte booleans and strings written
as `int32 length` + that many bytes. There is no index and no compression;
records simply follow each other until the end of the file.

Reader: [`tools/amc_export.py`](../tools/amc_export.py) (versions 3.1-4.2).

## Header

The file starts with a fixed 65-byte ANSI string that also tells the version:

```
 AMC_3.1 Ant Movie Catalog 3.1.x   www.buypin.com  www.ant.be.tf 
 AMC_3.3 Ant Movie Catalog 3.3.x   www.buypin.com  www.ant.be.tf 
 AMC_3.5 Ant Movie Catalog 3.5.x   www.buypin.com    www.antp.be 
 AMC_4.0 Ant Movie Catalog 4.0.x   antp/soulsnake    www.antp.be 
 AMC_4.1 Ant Movie Catalog 4.1.x   antp/soulsnake    www.antp.be 
 AMC_4.2 Ant Movie Catalog 4.2.x   antp/soulsnake    www.antp.be 
```

(note the leading and trailing space). Older 1.x-3.0 files are fixed-size
Pascal records and are not covered here.

## Catalog properties

```
string  owner name
string  owner e-mail
string  ICQ                      (only version < 3.5)
string  owner site
string  description
```

Version >= 4.0 then has the custom field definitions:

```
string  ColumnSettings
string  GUIProperties
int32   count
  per field:
    string tag
    string name
    string ext                   (>= 4.1)
    string type                  ("ftString", "ftInteger", "ftReal", "ftBoolean", "ftDate", "ftList", "ftText", "ftUrl" ...)
    string default value
    string mediainfo             (>= 4.1)
    bool   multivalues
    int32  separator, bool rmp, bool patch     (>= 4.1)
    bool   excluded in scripts
    string GUI properties
    if type == ftList:
      int32 count, string values...
      bool autoadd, bool sort, bool autocomplete, bool use catalog values   (>= 4.1)
```

## Movie record (repeated to end of file)

```
int32   number
int32   date added        (Delphi date: days since 1899-12-30)
int32   date watched      (>= 4.2)
int32   user rating       (>= 4.2)   x10, -1 = none
int32   rating                       x10 (< 3.5: x1), -1 = none
int32   year
int32   length (minutes)
int32   video bitrate
int32   audio bitrate
int32   disks
int32   color tag         (>= 4.1)
bool    checked
string  media label
string  media type        (>= 3.3)
string  source            (>= 3.3)
string  borrower
string  original title
string  translated title
string  director
string  producer
string  writer            (>= 4.2)
string  composer          (>= 4.2)
string  country
string  category
string  certification     (>= 4.2)
string  actors
string  URL
string  description
string  comments
string  file path         (>= 4.2)
string  video format
string  audio format
string  resolution
string  framerate
string  languages
string  subtitles
string  size
--- picture ---
string  picture path      (file name/relative path, or just the extension when stored inside)
int32   picture size      (0 = not stored; otherwise raw image bytes follow)
bytes   picture data
--- custom fields (>= 4.0): one string per defined field, in definition order ---
--- extras (>= 4.2) ---
int32   count
  per extra: bool checked, string tag, string title, string category, string url,
             string description, string comments, string created by, picture (as above)
```

Strings are ANSI in the code page of the machine that wrote the file (AMC
4.2 has no Unicode option); the reader tries UTF-8 first and falls back to
the code page given with `--encoding`. `-1` in numeric fields means "empty".

## Importing

All My Movies imports `.amc` directly (all versions listed above, including
pictures stored in the file, custom fields and the `strLanguages` audio
languages): <https://www.bolidesoft.com/ant-movie-catalog.html>.
