#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nizers_export.py - export a Movienizer / Booknizer / Medianizer database to CSV.

Movienizer (*.dmo), Booknizer (*.dbo) and Medianizer (*.dmb) share one SQLite
engine and one schema (see docs/nizers.md).  This script needs only the Python
standard library.

    python nizers_export.py "C:\\Users\\me\\Documents\\Movienizer\\My movies.dmo"
    python nizers_export.py collection.dmb --out export_dir --covers

Output (UTF-8 CSV with BOM, opens in Excel/LibreOffice directly):
    items.csv     one row per movie/book/album/game in the collection or wish list
    persons.csv   people linked to those items (actors, directors, authors...)
    episodes.csv  TV episodes (Movienizer/Medianizer)
    items.json    the same items with lists kept as lists
    covers/       (with --covers) front covers copied from the Covers folder

Only records that are in the collection or on the wish list are exported:
the programs keep every record you ever looked at (thousands of them), and
those are noise for a migration.  Pass --everything to dump all of them.
"""
import argparse
import csv
import json
import os
import shutil
import sqlite3
import sys

ITEM_TYPES = {0: "movie", 1: "music", 2: "book", 3: "game"}

# manuals.reference -> what the lookup list holds (movie databases)
REF = {
    1: "video_standard",   # NTSC, PAL
    2: "media_format",     # DVD, Blu-ray, VHS, (books: PDF, EPUB)
    3: "media_type",       # Movie, Television, Animation
    4: "screen_ratio",     # 16:9 (books: unused)
    5: "resolution",       # 1920 x 1080 (books: dimensions)
    6: "language",         # audio languages
    7: "audio_track",      # "Russian AC3 6 ch" (old-format books: languages)
    8: "genre",
    9: "country",          # (old-format books: city of publication)
    10: "location",        # My computer, Shelf, ... (used through table loans)
    11: "mpaa",
    12: "studio",          # (books: publisher)
    13: "custom",
    17: "tag",             # user labels
    19: "video_codec",
    20: "disc_label",
    21: "edition",
    22: "series",
    23: "subtitles",
    30: "instrument",      # music: person roles
}

# data.mode -> role of a person on a movie record
MOVIE_ROLES = {1: "director", 2: "writer", 3: "actor", 4: "character", 5: "producer", 6: "composer"}
# In book databases the same numbers mean different things.
BOOK_ROLES = {1: "editor", 3: "author", 4: "translator"}


def q(con, sql, params=()):
    return con.execute(sql, params).fetchall()


def columns(con, table):
    return [r[1] for r in q(con, "pragma table_info(%s)" % table)]


def lookup(con, ref):
    """All names of one lookup list keyed by code."""
    return {code: name for code, name in q(con, "SELECT code, name FROM manuals WHERE reference=?", (ref,))}


def export(path, out_dir, want_covers=False, everything=False):
    con = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    con.text_factory = lambda b: b.decode("utf-8", "replace")

    mcols = columns(con, "movies")
    has_item_type = "item_type" in mcols
    try:
        ver = q(con, "SELECT version FROM internal_data")[0][0]
    except Exception:
        ver = None
    print("schema version:", ver, "| item_type column:", has_item_type)

    lists = {ref: lookup(con, ref) for ref in REF}
    used = set()   # persons referenced by exported items

    # multi-valued lookups per item (genres, countries, studios, tags, ...)
    multi = {}
    for movie, ref, code in q(con, "SELECT movie, reference, ref_code FROM movies_manuals"):
        name = lists.get(ref, {}).get(code)
        if name:
            multi.setdefault(movie, {}).setdefault(REF.get(ref, "ref%d" % ref), []).append(name)

    # persons and their roles
    persons = {}
    for row in q(con, "SELECT code, name, original_name, birth_date, death_date, birthplace, imdb_code, biography FROM persons"):
        persons[row[0]] = dict(zip(["code", "name", "original_name", "birth_date", "death_date", "birthplace", "imdb_code", "biography"], row))
    roles = {}
    for movie, person, mode, order in q(con, "SELECT movie, person, mode, sort_order FROM data ORDER BY movie, mode, sort_order"):
        roles.setdefault(movie, []).append((mode, person))
    characters = {}
    if "characters" in [r[0] for r in q(con, "SELECT name FROM sqlite_master WHERE type='table'")]:
        for person, name, movie in q(con, "SELECT person, name, movie FROM characters"):
            characters[(movie, person)] = name

    # external ids / links
    links = {}
    for movie, code, script, site, rating in q(con, "SELECT movie, code, script, site, rating FROM movies_codes"):
        links.setdefault(movie, []).append({"script": script, "code": code, "url": site, "rating": rating})

    # images: mode 1 front cover, 6 person photo, 3 shots (paths relative to Covers\)
    covers = {}
    for movie, person, mode, rel in q(con, "SELECT movie, person, mode, path FROM images WHERE mode IN (1,6) ORDER BY sort_order, code"):
        if mode == 1 and movie and movie not in covers:
            covers[movie] = rel
        if mode == 6 and person and person in persons and "photo" not in persons[person]:
            persons[person]["photo"] = rel

    # current storage location lives in table loans (open record, no return_date)
    location = {}
    for movie, loc in q(con, "SELECT movie, location FROM loans WHERE COALESCE(return_date,'')='' ORDER BY code"):
        if movie:
            location[movie] = lists[10].get(loc, "")
    # editions carry file name, barcode, ISBN (books: features), disc number
    editions = {}
    for row in q(con, "SELECT movie, filename, barcode, features, disc_nom, duration, comment FROM editions ORDER BY movie, sort_order"):
        editions.setdefault(row[0], []).append(row[1:])

    where = "" if everything else "WHERE (in_collection=1 OR wanted=1)"
    sel = ["code", "title", "original_title", "year", "description", "comment", "duration", "imdb_code",
           "date_add", "date_update", "in_collection", "wanted", "seen", "rating", "imdb_rating",
           "media_format", "media_type", "resolution", "screen_ratio", "mpaa", "disc_nom", "disc_label",
           "movie_number", "tagline", "tomes_count", "series", "series_nom", "title_sort", "original_language"]
    sel = [c for c in sel if c in mcols] + (["item_type"] if has_item_type else [])
    items = []
    for row in q(con, "SELECT %s FROM movies %s ORDER BY code" % (", ".join(sel), where)):
        r = dict(zip(sel, row))
        code = r["code"]
        item_type = r.get("item_type", 0 if path.lower().endswith(".dmo") else 2 if path.lower().endswith(".dbo") else 0)
        kind = ITEM_TYPES.get(item_type, str(item_type))
        role_names = BOOK_ROLES if kind == "book" else MOVIE_ROLES
        it = {
            "id": code,
            "type": kind,
            "title": r.get("title") or "",
            "original_title": r.get("original_title") or "",
            "year": r.get("year"),
            "in_collection": bool(r.get("in_collection")),
            "wish_list": bool(r.get("wanted")),
            "seen": bool(r.get("seen")),
            "my_rating": r.get("rating"),
            "imdb_rating": r.get("imdb_rating"),
            "description": r.get("description") or "",
            "comment": r.get("comment") or "",
            "tagline": r.get("tagline") or "",
            "duration_min": r.get("duration"),
            "media_format": lists[2].get(r.get("media_format"), ""),
            "media_type": lists[3].get(r.get("media_type"), ""),
            "resolution": lists[5].get(r.get("resolution"), ""),
            "screen_ratio": lists[4].get(r.get("screen_ratio"), ""),
            "mpaa": lists[11].get(r.get("mpaa"), ""),
            "disc_label": lists[20].get(r.get("disc_label"), ""),
            "disc_number": "" if r.get("disc_nom") is None else str(r.get("disc_nom")),
            "number": r.get("movie_number"),
            "media_count": r.get("tomes_count"),
            "series": lists[22].get(r.get("series"), ""),
            "series_number": r.get("series_nom"),
            "location": location.get(code, ""),
            "added": r.get("date_add") or "",
            "updated": r.get("date_update") or "",
            "imdb": r.get("imdb_code") or "",
            "cover": covers.get(code, ""),
        }
        for key, col in (("genre", "genres"), ("country", "countries"), ("studio", "studios"), ("tag", "tags"),
                         ("language", "languages"), ("subtitles", "subtitles"), ("audio_track", "audio_tracks"),
                         ("video_codec", "video_codecs"), ("edition", "editions")):
            it[col] = multi.get(code, {}).get(key, [])
        for mode, person in roles.get(code, []):
            p = persons.get(person)
            if not p:
                continue
            role = role_names.get(mode, "role%d" % mode)
            entry = p["name"]
            ch = characters.get((code, person))
            if role == "actor" and ch:
                entry = "%s (%s)" % (entry, ch)
            it.setdefault(role + "s", []).append(entry)
            used.add(person)
        it["links"] = links.get(code, [])
        for l in it["links"]:
            if l["script"] == "kinopoisk" and l["url"]:
                it.setdefault("kinopoisk", l["url"])
            if l["script"] == "trailer" and l["url"]:
                it.setdefault("trailer", l["url"])
        eds = editions.get(code, [])
        it["files"] = [e[0] for e in eds if e[0]]
        it["barcodes"] = [e[1] for e in eds if e[1]]
        if kind == "book":
            # Booknizer keeps ISBN in editions.features (several separated by <br>)
            isbn = []
            for e in eds:
                if e[2]:
                    isbn += [s.strip() for s in e[2].replace("<br>", "\n").splitlines() if s.strip()]
            it["isbn"] = isbn
            it["pages"] = eds[0][4] if eds else None
        items.append(it)

    os.makedirs(out_dir, exist_ok=True)
    list_cols = [k for k in items[0].keys() if isinstance(items[0][k], list)] if items else []
    # rows for CSV: lists joined with "; ", links dropped
    fieldnames = []
    for it in items:
        for k in it:
            if k not in fieldnames and k != "links":
                fieldnames.append(k)
    with open(os.path.join(out_dir, "items.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for it in items:
            w.writerow({k: ("; ".join(map(str, v)) if isinstance(v, list) else v) for k, v in it.items() if k != "links"})
    with open(os.path.join(out_dir, "items.json"), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)

    with open(os.path.join(out_dir, "persons.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "original_name", "birth_date", "death_date", "birthplace", "imdb", "photo", "biography"])
        for code in sorted(used):
            p = persons[code]
            w.writerow([code, p["name"], p["original_name"] or "", p["birth_date"] or "", p["death_date"] or "",
                        p["birthplace"] or "", p["imdb_code"] or "", p.get("photo", ""), (p["biography"] or "").strip()])

    ids = {it["id"] for it in items}
    ep_rows = q(con, "SELECT movie, season, episode, title, original_title, original_air_date, description, seen, rating FROM episodes ORDER BY movie, season, episode")
    with open(os.path.join(out_dir, "episodes.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "season", "episode", "title", "original_title", "air_date", "description", "seen", "rating"])
        for row in ep_rows:
            if row[0] in ids:
                w.writerow(row)

    if want_covers:
        base = os.path.join(os.path.dirname(os.path.abspath(path)), "Covers")
        cdir = os.path.join(out_dir, "covers")
        os.makedirs(cdir, exist_ok=True)
        copied = 0
        for it in items:
            rel = it["cover"]
            if not rel:
                continue
            src = os.path.join(base, rel.replace("\\", os.sep))
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(cdir, "%d%s" % (it["id"], os.path.splitext(src)[1])))
                copied += 1
        print("covers copied:", copied, "from", base)

    print("items: %d (persons: %d, episodes: %d) -> %s" % (len(items), len(used), sum(1 for r in ep_rows if r[0] in ids), out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("database", help="*.dmo, *.dbo or *.dmb file")
    ap.add_argument("--out", help="output folder (default: <database>_export)")
    ap.add_argument("--covers", action="store_true", help="copy front covers from the Covers folder next to the database")
    ap.add_argument("--everything", action="store_true", help="export all records, not only collection + wish list")
    a = ap.parse_args()
    out = a.out or os.path.splitext(os.path.abspath(a.database))[0] + "_export"
    export(a.database, out, a.covers, a.everything)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
