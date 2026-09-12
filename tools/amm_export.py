#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
amm_export.py - export an All My Movies database (*.amm) to CSV / JSON and
pull the pictures out, without All My Movies and without Windows.

    pip install access-parser
    python amm_export.py "My Movies.amm"
    python amm_export.py "My Movies.amm" --out export --covers --all-images

Output folder:
    movies.csv / movies.json   one row per movie, people and lists joined with "; "
    episodes.csv               TV episodes
    persons.csv                actors, directors, writers
    friends.csv, loans.csv     who borrowed what and when
    settings.txt               database options that matter (e.g. where pictures live)
    covers/<MovieID>.jpg       (--covers)
    shots/, persons/, friends/ (--all-images)

Pictures are read from the database when the option "store images inside the
database" was on, otherwise from the folder <name>_images2 next to the file -
so keep that folder together with the .amm when copying.

Format notes: docs/allmymovies-amm.md.  Read-only: the .amm is never changed.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jetdb import JetDatabase                      # noqa: E402
from bolide_common import (database_settings, setting, images_folder, load_image, split_video_info,   # noqa: E402
                           audio_tracks, audio_summary, tenth, money, clean_date, write_csv, write_json,
                           by_id, group, save_settings_report)


def export(path, out_dir, covers=False, all_images=False):
    db = JetDatabase(path)
    if not db.has_table("movies") or not db.has_table("Actors"):
        sys.exit("This does not look like an All My Movies database (no movies/Actors tables).")
    print("Jet %d database, encrypted: %s, tables: %d" % (db.info["version"], db.info["encrypted"], len(db.tables)))
    settings = database_settings(db)
    inside = setting(settings, "main", "ImagesInside")
    folder = images_folder(path)
    # The option and the real storage can disagree (support cases), so pictures
    # are always looked up in both places: the blob first, then the file.
    print("option 'store images inside the database': %s; external folder %s%s" % (
        inside, folder, " (present)" if os.path.isdir(folder) else " (not found)"))

    names = {r["ActorID"]: r for r in db.rows("Actors")}
    countries = {r["CountryID"]: r["Name"] for r in db.rows("Countries")}
    genres = {r["GenreID"]: r["Name"] for r in db.rows("Genres")}
    media_types = {r["MediaTypeID"]: r["MediaTypeName"] for r in db.rows("MediaType")}
    locations = {r["MediaLocationID"]: r["Name"] for r in db.rows("MediaLocation")}
    qualities = {r["QualityID"]: r["Name"] for r in db.rows("QualityValues")}
    friends = by_id(db.rows("friends"), "FriendID")
    cfields = {r["FieldID"]: r["Name"] for r in db.rows("CustomFields")}
    cflags = {r["FlagID"]: r["Name"] for r in db.rows("CustomFlags")}

    actors_l = group(db.rows("ActorsLink"), "MovieID")
    directors_l = group(db.rows("DirectorLink"), "MovieID")
    writers_l = group(db.rows("ScenarioLink"), "MovieID")
    genres_l = group(db.rows("GenresLink"), "MovieID")
    countries_l = group(db.rows("CountryLink"), "MovieID", ("ID",))
    cfields_l = group(db.rows("CustomFieldsLink"), "MovieID", ("ID",))
    cflags_l = group(db.rows("CustomFlagsLink"), "MovieID", ("ID",))
    files_l = group(db.rows("FileLinks"), "MovieID", ("ID",))
    images_l = group(db.rows("images"), "MovieID", ("Sorter", "ID"))
    episodes_l = group(db.rows("Episodes"), "MovieID", ("SeasonNum", "EpisodeNum", "EpisodeID"))

    def person(aid):
        p = names.get(aid)
        return p["Name"] if p else ""

    movies = []
    for r in sorted(db.rows("movies"), key=lambda r: (r.get("movienum") or 0, r["MovieID"])):
        mid = r["MovieID"]
        tracks = audio_tracks(r.get("audioinfo"))
        m = {
            "id": mid,
            "number": r.get("movienum"),
            "title": r.get("Name") or "",
            "original_title": r.get("originaltitle") or "",
            "year": r.get("year") or "",
            "genres": [genres.get(l["GenreID"], "") for l in genres_l.get(mid, [])],
            "countries": [countries.get(l["CountryID"], "") for l in countries_l.get(mid, [])],
            "directors": [person(l["ActorID"]) for l in directors_l.get(mid, [])],
            "writers": [person(l["ActorID"]) for l in writers_l.get(mid, [])],
            "actors": ["%s (%s)" % (person(l["ActorID"]), l["Role"]) if l.get("Role") else person(l["ActorID"])
                       for l in actors_l.get(mid, [])],
            "studio": r.get("studio") or "",
            "length_min": r.get("length") or "",
            "rating": tenth(r.get("rating")),
            "my_rating": tenth(r.get("myrating")),
            "mpaa": r.get("mpaa") or "",
            "seen": bool(r.get("seen")),
            "wish_list": bool(r.get("wishlist")),
            "hidden": bool(r.get("hidden")),
            "description": r.get("description") or "",
            "comments": r.get("comments") or "",
            "url": r.get("url") or "",
            "trailer": r.get("Trailer") or "",
            "barcode": r.get("barcode") or "",
            "media_type": media_types.get(r.get("mediatypeID"), ""),
            "media_label": r.get("medialabel") or "",
            "media_count": r.get("mediacount"),
            "location": locations.get(r.get("medialocationID"), ""),
            "quality": qualities.get(r.get("qualityID"), ""),
            "file": r.get("LocalPath") or "",
            "files": ["%s|%s" % (l.get("Title") or "", l.get("Filename") or "") for l in files_l.get(mid, [])],
            "size": r.get("size") or "",
            "resolution": r.get("resolution") or "",
            "aspect_ratio": r.get("aspectratio") or "",
            "subtitles": r.get("subtitles") or "",
            "audio": audio_summary(tracks),
            "audio_tracks": tracks,
            "price": money(r.get("Price")),
            "added": clean_date(r.get("adddate")),
            "modified": clean_date(r.get("Modified")),
            "loaned_to": friends.get(r.get("LoanFriendID"), {}).get("Name", "") if r.get("loan") else "",
            "loan_date": clean_date(r.get("loan")),
            "return_by": clean_date(r.get("returndate")),
            "borrowed_from": friends.get(r.get("BorrowFriendID"), {}).get("Name", ""),
            "flags": [cflags.get(l["FlagID"], "") for l in cflags_l.get(mid, []) if l.get("Value")],
            "episodes": len(episodes_l.get(mid, [])),
        }
        m.update(split_video_info(r.get("videoinfo")))
        for l in cfields_l.get(mid, []):
            m["custom:" + cfields.get(l["FieldID"], str(l["FieldID"]))] = l.get("Value") or ""
        imgs = images_l.get(mid, [])
        cover = next((i for i in imgs if i.get("cover")), None)
        m["cover_image_id"] = cover["ID"] if cover else ""
        m["shots"] = len([i for i in imgs if not i.get("cover")])
        movies.append(m)

    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "movies.csv"), [{k: v for k, v in m.items() if k != "audio_tracks"} for m in movies])
    write_json(os.path.join(out_dir, "movies.json"), movies)

    episodes = []
    for mid, eps in episodes_l.items():
        title = next((m["title"] for m in movies if m["id"] == mid), "")
        for e in eps:
            episodes.append({"movie_id": mid, "movie": title, "season": e.get("SeasonNum"), "episode": e.get("EpisodeNum"),
                             "title": e.get("EpisodeTitle") or "", "air_date": e.get("AirDate") or "",
                             "seen": bool(e.get("seen")), "rating": tenth(e.get("rating")), "watched_on": clean_date(e.get("mydate")),
                             "description": e.get("Description") or "", "comments": e.get("Comments") or "",
                             "url": e.get("URL") or "", "file": e.get("localpath") or ""})
    write_csv(os.path.join(out_dir, "episodes.csv"), episodes)

    persons = []
    for aid, p in sorted(names.items(), key=lambda kv: (kv[1].get("Name") or "")):
        persons.append({"id": aid, "name": p.get("Name") or "", "alt_name": p.get("AltName") or "",
                        "birth_day": p.get("BirthDay") or "", "birth_year": p.get("BirthYear") or "",
                        "death_year": p.get("DeathYear") or "", "birth_place": p.get("BirthPlace") or "",
                        "country": countries.get(p.get("CountryID"), ""), "url": p.get("URL") or "",
                        "rating": tenth(p.get("Rating")), "biography": p.get("biography") or "",
                        "filmography": p.get("filmography") or "", "comments": p.get("Comments") or ""})
    write_csv(os.path.join(out_dir, "persons.csv"), persons)

    write_csv(os.path.join(out_dir, "friends.csv"),
              [{"id": f["FriendID"], "name": f.get("Name") or "", "phone": f.get("Phone") or "", "email": f.get("Email") or "",
                "address": f.get("Address") or "", "comments": f.get("Comments") or ""} for f in friends.values()])
    titles = {m["id"]: m["title"] for m in movies}
    write_csv(os.path.join(out_dir, "loans.csv"),
              [{"movie_id": l["MovieID"], "movie": titles.get(l["MovieID"], ""), "friend": friends.get(l["FriendID"], {}).get("Name", ""),
                "loaned": clean_date(l.get("Loan")), "due": clean_date(l.get("Overdue")), "returned": clean_date(l.get("return"))}
               for l in sorted(db.rows("LoanHistory"), key=lambda l: l.get("HistID") or 0)])
    save_settings_report(os.path.join(out_dir, "settings.txt"), settings)

    saved = 0
    if covers or all_images:
        cdir = os.path.join(out_dir, "covers")
        sdir = os.path.join(out_dir, "shots")
        os.makedirs(cdir, exist_ok=True)
        for mid, imgs in images_l.items():
            n = 0
            for i in imgs:
                data = load_image(i.get("image"), folder, "m", i["ID"])
                if not data:
                    continue
                if i.get("cover"):
                    target = os.path.join(cdir, "%d.jpg" % mid)
                elif all_images:
                    n += 1
                    os.makedirs(sdir, exist_ok=True)
                    target = os.path.join(sdir, "%d_%d.jpg" % (mid, n))
                else:
                    continue
                with open(target, "wb") as fh:
                    fh.write(data)
                saved += 1
    if all_images:
        pdir = os.path.join(out_dir, "persons")
        os.makedirs(pdir, exist_ok=True)
        for aid, imgs in group(db.rows("ActorImages"), "ActorID").items():
            for n, i in enumerate(imgs, 1):
                data = load_image(i.get("image"), folder, "a", i["ID"])
                if data:
                    with open(os.path.join(pdir, "%d_%d.jpg" % (aid, n)), "wb") as fh:
                        fh.write(data)
                    saved += 1
        fdir = os.path.join(out_dir, "friends")
        os.makedirs(fdir, exist_ok=True)
        for fid, imgs in group(db.rows("FriendImages"), "FriendID", ("ID",)).items():
            for n, i in enumerate(imgs, 1):
                data = load_image(i.get("image"), folder, "f", i["ID"])
                if data:
                    with open(os.path.join(fdir, "%d_%d.jpg" % (fid, n)), "wb") as fh:
                        fh.write(data)
                    saved += 1
    print("movies: %d, episodes: %d, persons: %d, loans: %d, pictures saved: %d -> %s" % (
        len(movies), len(episodes), len(persons), len(db.rows("LoanHistory")), saved, out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("database", help="*.amm file")
    ap.add_argument("--out", help="output folder (default: <database>_export)")
    ap.add_argument("--covers", action="store_true", help="save front covers as covers/<id>.jpg")
    ap.add_argument("--all-images", action="store_true", help="also screenshots, person photos and friend photos")
    a = ap.parse_args()
    export(a.database, a.out or os.path.splitext(os.path.abspath(a.database))[0] + "_export", a.covers, a.all_images)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
