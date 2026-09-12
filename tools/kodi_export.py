#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kodi_export.py - export the Kodi video library (MyVideosNNN.db) to CSV.

Kodi keeps the scraped library in an SQLite file whose name carries the schema
version: MyVideos116.db (Kodi 18), 119 (19), 121 (20), 131 (21).  Where it is:

    Windows   %APPDATA%\\Kodi\\userdata\\Database\\
    Linux     ~/.kodi/userdata/Database/
    macOS     ~/Library/Application Support/Kodi/userdata/Database/
    Android   /sdcard/Android/data/org.xbmc.kodi/files/.kodi/userdata/Database/

Copy the file somewhere first if Kodi is running.  Only the standard library
is needed.

    python kodi_export.py "%APPDATA%\\Kodi\\userdata\\Database\\MyVideos131.db"
    python kodi_export.py MyVideos131.db --out kodi_export

Output: movies.csv, tvshows.csv, episodes.csv, persons.csv, movies.json.
Schema notes are in docs/kodi.md.  Databases older than schema 107 (Kodi 17)
lack the actor_link / rating / uniqueid tables and are not handled.
"""
import argparse
import csv
import json
import os
import sqlite3
import sys


def q(con, sql, params=()):
    return con.execute(sql, params).fetchall()


def split_multi(s):
    """Kodi stores genre/country/studio lists as 'A / B / C' in the movie row."""
    return [p.strip() for p in (s or "").split(" / ") if p.strip()]


def export(path, out_dir):
    con = sqlite3.connect("file:%s?mode=ro" % path.replace("\\", "/"), uri=True)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    ver = q(con, "SELECT idVersion FROM version")[0][0]
    print("schema version:", ver)
    if ver < 107:
        sys.exit("Database schema %d is too old (Kodi 17 or newer expected)." % ver)

    files = {}
    for idf, fname, ppath, play, last, added in q(con,
            "SELECT f.idFile, f.strFilename, p.strPath, f.playCount, f.lastPlayed, f.dateAdded "
            "FROM files f JOIN path p ON p.idPath=f.idPath"):
        files[idf] = {"file": (ppath or "") + (fname or ""), "play_count": play or 0,
                      "last_played": last or "", "added": added or ""}

    streams = {}
    for row in q(con, "SELECT idFile, iStreamType, strVideoCodec, iVideoWidth, iVideoHeight, iVideoDuration, "
                      "strAudioCodec, iAudioChannels, strAudioLanguage, strSubtitleLanguage FROM streamdetails"):
        s = streams.setdefault(row[0], {"video": "", "audio": [], "subtitles": []})
        if row[1] == 0 and row[2]:
            s["video"] = "%s %sx%s" % (row[2], row[3], row[4])
            s["duration_sec"] = row[5]
        elif row[1] == 1:
            s["audio"].append(" ".join(str(x) for x in (row[8], row[6], "%sch" % row[7] if row[7] else "") if x))
        elif row[1] == 2 and row[9]:
            s["subtitles"].append(row[9])

    def people(media_type, media_id):
        out = {"directors": [], "writers": [], "actors": []}
        for name, in q(con, "SELECT a.name FROM director_link l JOIN actor a ON a.actor_id=l.actor_id "
                            "WHERE l.media_type=? AND l.media_id=?", (media_type, media_id)):
            out["directors"].append(name)
        for name, in q(con, "SELECT a.name FROM writer_link l JOIN actor a ON a.actor_id=l.actor_id "
                            "WHERE l.media_type=? AND l.media_id=?", (media_type, media_id)):
            out["writers"].append(name)
        for name, role in q(con, "SELECT a.name, l.role FROM actor_link l JOIN actor a ON a.actor_id=l.actor_id "
                                 "WHERE l.media_type=? AND l.media_id=? ORDER BY l.cast_order", (media_type, media_id)):
            out["actors"].append("%s (%s)" % (name, role) if role else name)
        return out

    def ids(media_type, media_id):
        return {t: v for v, t in q(con, "SELECT value, type FROM uniqueid WHERE media_type=? AND media_id=?", (media_type, media_id))}

    def rating(media_type, media_id, rating_id):
        r = q(con, "SELECT rating_type, rating, votes FROM rating WHERE rating_id=?", (rating_id,)) if rating_id else []
        if not r:
            r = q(con, "SELECT rating_type, rating, votes FROM rating WHERE media_type=? AND media_id=? LIMIT 1", (media_type, media_id))
        return {"source": r[0][0], "rating": round(r[0][1], 1), "votes": r[0][2]} if r else {}

    def art(media_type, media_id):
        d = {}
        for t, url in q(con, "SELECT type, url FROM art WHERE media_type=? AND media_id=?", (media_type, media_id)):
            if url and not url.startswith("image://video@"):
                d[t] = url
        return d

    movies = []
    sets = {sid: name for sid, name in q(con, "SELECT idSet, strSet FROM sets")}
    for row in q(con, "SELECT idMovie, idFile, c00, c01, c03, c05, c06, c11, c12, c14, c15, c16, c18, c19, c21, "
                      "idSet, userrating, premiered FROM movie ORDER BY idMovie"):
        (mid, idf, title, plot, tagline, rating_id, writers, runtime, mpaa, genre, director,
         orig, studio, trailer, country, idset, userrating, premiered) = row
        f = files.get(idf, {})
        p = people("movie", mid)
        m = {
            "id": mid,
            "title": title or "",
            "original_title": orig or "",
            "year": (premiered or "")[:4],
            "premiered": premiered or "",
            "plot": plot or "",
            "tagline": tagline or "",
            "runtime_min": int(runtime) // 60 if runtime and str(runtime).isdigit() else "",
            "mpaa": mpaa or "",
            "genres": split_multi(genre),
            "countries": split_multi(country),
            "studios": split_multi(studio),
            "directors": p["directors"] or split_multi(director),
            "writers": p["writers"] or split_multi(writers),
            "actors": p["actors"],
            "set": sets.get(idset, ""),
            "user_rating": userrating or "",
            "rating": rating("movie", mid, rating_id),
            "ids": ids("movie", mid),
            "trailer": (trailer or "").replace("plugin://plugin.video.youtube/play/?video_id=", "https://www.youtube.com/watch?v="),
            "file": f.get("file", ""),
            "play_count": f.get("play_count", 0),
            "last_played": f.get("last_played", ""),
            "added": f.get("added", ""),
            "art": art("movie", mid),
        }
        m.update({"video": streams.get(idf, {}).get("video", ""),
                  "audio": streams.get(idf, {}).get("audio", []),
                  "subtitles": streams.get(idf, {}).get("subtitles", [])})
        movies.append(m)

    shows = []
    for row in q(con, "SELECT idShow, c00, c01, c05, c08, c09, c13, c14, c16, userrating FROM tvshow ORDER BY idShow"):
        sid, title, plot, premiered, genre, orig, mpaa, studio, trailer, userrating = row
        p = people("tvshow", sid)
        paths = [pp for pp, in q(con, "SELECT p.strPath FROM tvshowlinkpath l JOIN path p ON p.idPath=l.idPath WHERE l.idShow=?", (sid,))]
        shows.append({
            "id": sid, "title": title or "", "original_title": orig or "", "premiered": premiered or "",
            "year": (premiered or "")[:4], "plot": plot or "", "mpaa": mpaa or "",
            "genres": split_multi(genre), "studios": split_multi(studio),
            "actors": p["actors"], "user_rating": userrating or "",
            "rating": rating("tvshow", sid, None), "ids": ids("tvshow", sid),
            "trailer": trailer or "", "paths": paths, "art": art("tvshow", sid),
        })

    episodes = []
    for row in q(con, "SELECT idEpisode, idShow, idFile, c00, c01, c05, c12, c13, userrating FROM episode ORDER BY idShow, CAST(c12 AS INTEGER), CAST(c13 AS INTEGER)"):
        eid, sid, idf, title, plot, aired, season, ep, userrating = row
        f = files.get(idf, {})
        episodes.append({"show_id": sid, "season": season, "episode": ep, "title": title or "",
                         "aired": aired or "", "plot": plot or "", "user_rating": userrating or "",
                         "file": f.get("file", ""), "play_count": f.get("play_count", 0),
                         "ids": ids("episode", eid)})

    persons = q(con, "SELECT a.actor_id, a.name, a.art_urls FROM actor a WHERE a.actor_id IN "
                     "(SELECT actor_id FROM actor_link UNION SELECT actor_id FROM director_link UNION SELECT actor_id FROM writer_link) ORDER BY a.name")

    os.makedirs(out_dir, exist_ok=True)

    def write_csv(name, rows):
        if not rows:
            return
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows:
                flat = {}
                for k, v in r.items():
                    if isinstance(v, list):
                        flat[k] = "; ".join(map(str, v))
                    elif isinstance(v, dict):
                        flat[k] = "; ".join("%s=%s" % kv for kv in v.items())
                    else:
                        flat[k] = v
                w.writerow(flat)

    write_csv("movies.csv", movies)
    write_csv("tvshows.csv", shows)
    write_csv("episodes.csv", episodes)
    with open(os.path.join(out_dir, "persons.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "name", "thumb"])
        for pid, name, art_urls in persons:
            # older Kodi wrote <thumb>url</thumb>, Kodi 21 writes the bare URL
            thumb = art_urls or ""
            if "<thumb" in thumb:
                thumb = thumb.split(">", 1)[1].split("<", 1)[0]
            w.writerow([pid, name, thumb])
    with open(os.path.join(out_dir, "movies.json"), "w", encoding="utf-8") as fh:
        json.dump({"movies": movies, "tvshows": shows, "episodes": episodes}, fh, ensure_ascii=False, indent=1)
    print("movies: %d, tv shows: %d, episodes: %d, persons: %d -> %s" % (len(movies), len(shows), len(episodes), len(persons), out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("database", help="MyVideosNNN.db (copy it if Kodi is running)")
    ap.add_argument("--out", help="output folder (default: <database>_export)")
    a = ap.parse_args()
    export(a.database, a.out or os.path.splitext(os.path.abspath(a.database))[0] + "_export")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
