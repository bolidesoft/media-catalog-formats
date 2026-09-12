#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
amc_export.py - read an Ant Movie Catalog binary catalog (*.amc) and export it
to CSV / JSON, optionally extracting the pictures stored inside the file.

Ant Movie Catalog (https://www.antp.be/software/moviecatalog) is open source
and can export XML itself, but people often have only the .amc file left.
This reader understands the binary format of versions 3.1 to 4.2 (the format
is described in docs/ant-movie-catalog.md).  Standard library only.

    python amc_export.py catalog.amc
    python amc_export.py catalog.amc --out amc_export --pictures --encoding cp1251

Strings inside .amc are ANSI in the code page of the machine that wrote the
file (AMC 4.2 has no Unicode mode).  The default is the current Windows ANSI
code page, or cp1252 elsewhere; use --encoding when accents or Cyrillic look
wrong.
"""
import argparse
import csv
import datetime
import json
import locale
import os
import struct
import sys

HEADERS = {
    "31": b" AMC_3.1 Ant Movie Catalog 3.1.x   www.buypin.com  www.ant.be.tf ",
    "33": b" AMC_3.3 Ant Movie Catalog 3.3.x   www.buypin.com  www.ant.be.tf ",
    "35": b" AMC_3.5 Ant Movie Catalog 3.5.x   www.buypin.com    www.antp.be ",
    "40": b" AMC_4.0 Ant Movie Catalog 4.0.x   antp/soulsnake    www.antp.be ",
    "41": b" AMC_4.1 Ant Movie Catalog 4.1.x   antp/soulsnake    www.antp.be ",
    "42": b" AMC_4.2 Ant Movie Catalog 4.2.x   antp/soulsnake    www.antp.be ",
}
HEADER_LEN = 65
PIC_EXT = {b"\xff\xd8": ".jpg", b"\x89P": ".png", b"GI": ".gif", b"BM": ".bmp"}


class Reader:
    def __init__(self, data, encoding):
        self.data = data
        self.pos = 0
        self.encoding = encoding

    def int32(self):
        v, = struct.unpack_from("<i", self.data, self.pos)
        self.pos += 4
        return v

    def bool(self):
        v = self.data[self.pos]
        self.pos += 1
        return bool(v)

    def string(self):
        n = self.int32()
        if n <= 0:
            return ""
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        # Unicode builds of AMC and third-party writers store UTF-8; a valid
        # UTF-8 sequence with high bytes is far more likely to be UTF-8 than
        # accidental ANSI text that happens to decode.
        if any(b >= 0x80 for b in raw):
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return raw.decode(self.encoding, errors="replace")

    def blob(self):
        n = self.int32()
        if n <= 0:
            return b""
        raw = self.data[self.pos:self.pos + n]
        self.pos += n
        return raw

    def eof(self):
        return self.pos >= len(self.data)


def delphi_date(days):
    """AMC stores dates as the integer part of a Delphi TDateTime (days since 1899-12-30)."""
    if not days or days <= 0:
        return ""
    return (datetime.date(1899, 12, 30) + datetime.timedelta(days=days)).isoformat()


def read_picture(r):
    path = r.string()
    blob = r.blob()
    return path, blob


def read_custom_field_properties(r, version):
    """Catalog-level definitions of custom fields (version >= 40)."""
    props = {"ColumnSettings": r.string(), "GUIProperties": r.string()}
    fields = []
    for _ in range(r.int32()):
        tag = r.string()
        f = {"tag": tag, "name": r.string()}
        if version >= 41:
            f["ext"] = r.string()
        f["type"] = r.string()
        f["default"] = r.string()
        if version >= 41:
            f["mediainfo"] = r.string()
        f["multivalues"] = r.bool()
        if version >= 41:
            r.int32()   # separator char
            r.bool()    # remove punctuation
            r.bool()    # patch
        r.bool()        # excluded in scripts
        f["gui"] = r.string()
        if f["type"] == "ftList":
            f["list_values"] = [r.string() for _ in range(r.int32())]
            if version >= 41:
                r.bool()  # ListAutoAdd
                r.bool()  # ListSort
                r.bool()  # ListAutoComplete
                r.bool()  # ListUseCatalogValues
        fields.append(f)
    props["fields"] = fields
    return props


def read_extra(r, version):
    e = {"checked": r.bool(), "tag": r.string(), "title": r.string(), "category": r.string(),
         "url": r.string(), "description": r.string(), "comments": r.string(), "created_by": r.string()}
    e["picture_path"], e["picture"] = read_picture(r)
    return e


def read_movie(r, version, custom_tags):
    m = {}
    m["number"] = r.int32()
    m["date_added"] = delphi_date(r.int32())
    if version >= 42:
        m["date_watched"] = delphi_date(r.int32())
        m["user_rating"] = r.int32()
    rating = r.int32()
    if version < 35 and rating != -1:
        rating *= 10
    m["rating"] = rating          # 0..100, -1 = none; divide by 10
    m["year"] = r.int32()
    m["length"] = r.int32()
    m["video_bitrate"] = r.int32()
    m["audio_bitrate"] = r.int32()
    m["disks"] = r.int32()
    if version >= 41:
        m["color_tag"] = r.int32()
    m["checked"] = r.bool()
    m["media"] = r.string()
    if version >= 33:
        m["media_type"] = r.string()
        m["source"] = r.string()
    m["borrower"] = r.string()
    m["original_title"] = r.string()
    m["translated_title"] = r.string()
    m["director"] = r.string()
    m["producer"] = r.string()
    if version >= 42:
        m["writer"] = r.string()
        m["composer"] = r.string()
    m["country"] = r.string()
    m["category"] = r.string()
    if version >= 42:
        m["certification"] = r.string()
    m["actors"] = r.string()
    m["url"] = r.string()
    m["description"] = r.string()
    m["comments"] = r.string()
    if version >= 42:
        m["file_path"] = r.string()
    m["video_format"] = r.string()
    m["audio_format"] = r.string()
    m["resolution"] = r.string()
    m["framerate"] = r.string()
    m["languages"] = r.string()
    m["subtitles"] = r.string()
    m["size"] = r.string()
    m["picture_path"], m["picture"] = read_picture(r)
    if version >= 40:
        m["custom"] = {tag: r.string() for tag in custom_tags}
    if version >= 42:
        m["extras"] = [read_extra(r, version) for _ in range(r.int32())]
    return m


def read_catalog(path, encoding):
    data = open(path, "rb").read()
    head = data[:HEADER_LEN]
    version = None
    for v, h in HEADERS.items():
        if head == h:
            version = int(v)
    if version is None:
        if head.startswith(b" AMC_"):
            raise SystemExit("AMC version %r is not supported (3.1-4.2 only)" % head[1:8])
        raise SystemExit("not an Ant Movie Catalog binary file: %s" % path)
    r = Reader(data, encoding)
    r.pos = HEADER_LEN
    cat = {"version": version, "owner": {}}
    cat["owner"]["name"] = r.string()
    cat["owner"]["mail"] = r.string()
    if version < 35:
        r.string()  # old ICQ field
    cat["owner"]["site"] = r.string()
    cat["owner"]["description"] = r.string()
    custom_tags = []
    if version >= 40:
        cat["custom_fields"] = read_custom_field_properties(r, version)
        custom_tags = [f["tag"] for f in cat["custom_fields"]["fields"]]
    movies = []
    while not r.eof():
        start = r.pos
        try:
            movies.append(read_movie(r, version, custom_tags))
        except (struct.error, IndexError):
            print("warning: file truncated or unknown layout at offset %d after %d movies" % (start, len(movies)))
            break
    cat["movies"] = movies
    return cat


def export(path, out_dir, encoding, pictures):
    cat = read_catalog(path, encoding)
    os.makedirs(out_dir, exist_ok=True)
    pic_dir = os.path.join(out_dir, "pictures")
    rows = []
    stored = 0
    for m in cat["movies"]:
        row = {k: v for k, v in m.items() if k not in ("picture", "extras", "custom")}
        for k in ("rating", "user_rating"):
            if k in row:
                row[k] = "" if row[k] in (-1, None) else row[k] / 10.0
        for tag, val in m.get("custom", {}).items():
            row["custom:" + tag] = val
        if m["picture"]:
            stored += 1
            if pictures:
                os.makedirs(pic_dir, exist_ok=True)
                ext = os.path.splitext(m["picture_path"])[1] or PIC_EXT.get(m["picture"][:2], ".bin")
                name = "%d%s" % (m["number"], ext)
                with open(os.path.join(pic_dir, name), "wb") as f:
                    f.write(m["picture"])
                row["picture_path"] = "pictures/" + name
        row["extras"] = "; ".join(e["title"] for e in m.get("extras", []) if e.get("title"))
        rows.append(row)
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(os.path.join(out_dir, "movies.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    slim = dict(cat)
    slim["movies"] = [{k: v for k, v in m.items() if k != "picture"} for m in cat["movies"]]
    for m in slim["movies"]:
        for e in m.get("extras", []):
            e.pop("picture", None)
    with open(os.path.join(out_dir, "movies.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=1)
    print("AMC %.1f: %d movies, %d with embedded pictures -> %s" % (cat["version"] / 10.0, len(rows), stored, out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("catalog", help="*.amc file")
    ap.add_argument("--out", help="output folder (default: <catalog>_export)")
    ap.add_argument("--pictures", action="store_true", help="extract pictures embedded in the catalog")
    ap.add_argument("--encoding", help="ANSI code page of the strings (default: system code page or cp1252)")
    a = ap.parse_args()
    enc = a.encoding or (locale.getpreferredencoding(False) if sys.platform == "win32" else "cp1252")
    export(a.catalog, a.out or os.path.splitext(os.path.abspath(a.catalog))[0] + "_export", enc, a.pictures)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
