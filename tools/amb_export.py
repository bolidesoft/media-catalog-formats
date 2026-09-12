#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
amb_export.py - export an All My Books database (*.amb) to CSV / JSON and pull
the covers out, without All My Books and without Windows.

    pip install access-parser
    python amb_export.py "My Books.amb"
    python amb_export.py "My Books.amb" --out export --covers --all-images

Output folder:
    books.csv / books.json     one row per book, authors and subjects joined with "; "
    authors.csv                authors, editors, translators, illustrators
    friends.csv, loans.csv     who borrowed what and when
    settings.txt               database options that matter (e.g. where pictures live)
    covers/<BookID>.jpg        (--covers)
    shots/, authors/, friends/ (--all-images)

Pictures are read from the database when the option "store images inside the
database" was on, otherwise from the folder <name>_images2 next to the file -
keep that folder together with the .amb when copying.

Format notes: docs/allmybooks-amb.md.  Read-only: the .amb is never changed.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jetdb import JetDatabase                      # noqa: E402
from bolide_common import (database_settings, setting, images_folder, load_image, tenth, money, clean_date,   # noqa: E402
                           write_csv, write_json, by_id, group, save_settings_report)


def export(path, out_dir, covers=False, all_images=False):
    db = JetDatabase(path)
    if not db.has_table("books") or not db.has_table("Authors"):
        sys.exit("This does not look like an All My Books database (no books/Authors tables).")
    print("Jet %d database, encrypted: %s, tables: %d" % (db.info["version"], db.info["encrypted"], len(db.tables)))
    settings = database_settings(db)
    inside = setting(settings, "main", "ImagesInside")
    folder = images_folder(path)
    # The option and the real storage can disagree (support cases), so pictures
    # are always looked up in both places: the blob first, then the file.
    print("option 'store images inside the database': %s; external folder %s%s" % (
        inside, folder, " (present)" if os.path.isdir(folder) else " (not found)"))

    authors = {r["AuthorID"]: r for r in db.rows("Authors")}
    subjects = {r["SubjID"]: r["Name"] for r in db.rows("Subjects")}
    bindings = {r["BindID"]: r["BindName"] for r in db.rows("Bindings")}
    locations = {r["LocationID"]: r["Name"] for r in db.rows("Location")}
    friends = by_id(db.rows("friends"), "FriendID")
    cfields = {r["FieldID"]: r["Name"] for r in db.rows("CustomFields")}
    cflags = {r["FlagID"]: r["Name"] for r in db.rows("CustomFlags")}

    links = {}
    for role, table in (("authors", "AuthorsLink"), ("editors", "EditorsLink"),
                        ("translators", "TranslatorsLink"), ("illustrators", "IllustratorsLink")):
        links[role] = group(db.rows(table), "BookID")
    subjects_l = group(db.rows("SubjectsLink"), "BookID")
    cfields_l = group(db.rows("CustomFieldsLink"), "BookID", ("ID",))
    cflags_l = group(db.rows("CustomFlagsLink"), "BookID", ("ID",))
    files_l = group(db.rows("FileLinks"), "BookID", ("ID",))
    images_l = group(db.rows("images"), "BookID", ("Sorter", "ID"))

    def person(aid):
        p = authors.get(aid)
        return p["Name"] if p else ""

    books = []
    for r in sorted(db.rows("books"), key=lambda r: (r.get("booknum") or 0, r["BookID"])):
        bid = r["BookID"]
        b = {
            "id": bid,
            "number": r.get("booknum"),
            "title": r.get("title") or "",
            "original_title": r.get("originaltitle") or "",
            "authors": ["%s (%s)" % (person(l["AuthorID"]), l["Role"]) if l.get("Role") else person(l["AuthorID"])
                        for l in links["authors"].get(bid, [])],
            "editors": [person(l["AuthorID"]) for l in links["editors"].get(bid, [])],
            "translators": [person(l["AuthorID"]) for l in links["translators"].get(bid, [])],
            "illustrators": [person(l["AuthorID"]) for l in links["illustrators"].get(bid, [])],
            "series": r.get("serie") or "",
            "series_2": r.get("Series2") or "",
            "volume": r.get("Volume") or "",
            "isbn": r.get("ISBN") or "",
            "year": r.get("year") if (r.get("year") or 0) > 0 else "",
            "publisher": r.get("publisher") or "",
            "language": r.get("language") or "",
            "pages": r.get("pages") if (r.get("pages") or 0) > 0 else "",
            "binding": bindings.get(r.get("BindID"), ""),
            "dimensions": r.get("dimensions") or "",
            "circulation": r.get("circulation") or "",
            "price": money(r.get("price")),
            "subjects": [subjects.get(l["SubjID"], "") for l in subjects_l.get(bid, [])],
            "rating": tenth(r.get("rating")),
            "my_rating": tenth(r.get("myrating")),
            "read": not bool(r.get("unread")),
            "date_read": clean_date(r.get("dateread")),
            "wish_list": bool(r.get("wishlist")),
            "location": locations.get(r.get("locationID"), ""),
            "synopsis": r.get("synopsis") or "",
            "contents": r.get("contents") or "",
            "comments": r.get("comments") or "",
            "url": r.get("url") or "",
            "file": r.get("LocalPath") or "",
            "file_size": r.get("FSize") or "",
            "files": ["%s|%s" % (l.get("Title") or "", l.get("Filename") or "") for l in files_l.get(bid, [])],
            "playtime": r.get("playtime") or "",
            "lcc": r.get("loc") or "",
            "dewey": r.get("dewey") or "",
            "added": clean_date(r.get("adddate")),
            "modified": clean_date(r.get("modified")),
            "loaned_to": friends.get(r.get("LoanFriendID"), {}).get("Name", "") if r.get("loan") else "",
            "loan_date": clean_date(r.get("loan")),
            "return_by": clean_date(r.get("returndate")),
            "borrowed_from": friends.get(r.get("BorrowFriendID"), {}).get("Name", ""),
            "flags": [cflags.get(l["FlagID"], "") for l in cflags_l.get(bid, []) if l.get("Value")],
        }
        for l in cfields_l.get(bid, []):
            b["custom:" + cfields.get(l["FieldID"], str(l["FieldID"]))] = l.get("Value") or ""
        imgs = images_l.get(bid, [])
        cover = next((i for i in imgs if i.get("cover")), None)
        b["cover_image_id"] = cover["ID"] if cover else ""
        b["extra_images"] = len([i for i in imgs if not i.get("cover")])
        books.append(b)

    os.makedirs(out_dir, exist_ok=True)
    write_csv(os.path.join(out_dir, "books.csv"), books)
    write_json(os.path.join(out_dir, "books.json"), books)

    rows = []
    for aid, p in sorted(authors.items(), key=lambda kv: (kv[1].get("Name") or "")):
        rows.append({"id": aid, "name": p.get("Name") or "", "alt_name": p.get("AltName") or "",
                     "birth_day": p.get("BirthDay") or "", "birth_year": p.get("BirthYear") or "",
                     "death_year": p.get("DeathYear") or "", "birth_place": p.get("BirthPlace") or "",
                     "country": p.get("Country") or "", "url": p.get("URL") or "",
                     "biography": p.get("biography") or "", "bibliography": p.get("bibliography") or "",
                     "comments": p.get("Comments") or ""})
    write_csv(os.path.join(out_dir, "authors.csv"), rows)

    write_csv(os.path.join(out_dir, "friends.csv"),
              [{"id": f["FriendID"], "name": f.get("Name") or "", "phone": f.get("Phone") or "", "email": f.get("Email") or "",
                "address": f.get("Address") or "", "comments": f.get("Comments") or ""} for f in friends.values()])
    titles = {b["id"]: b["title"] for b in books}
    write_csv(os.path.join(out_dir, "loans.csv"),
              [{"book_id": l["BookID"], "book": titles.get(l["BookID"], ""), "friend": friends.get(l["FriendID"], {}).get("Name", ""),
                "loaned": clean_date(l.get("Loan")), "due": clean_date(l.get("Overdue")), "returned": clean_date(l.get("return"))}
               for l in sorted(db.rows("LoanHistory"), key=lambda l: l.get("HistID") or 0)])
    save_settings_report(os.path.join(out_dir, "settings.txt"), settings)

    saved = 0
    if covers or all_images:
        cdir = os.path.join(out_dir, "covers")
        sdir = os.path.join(out_dir, "shots")
        os.makedirs(cdir, exist_ok=True)
        for bid, imgs in images_l.items():
            n = 0
            for i in imgs:
                data = load_image(i.get("image"), folder, "m", i["ID"])
                if not data:
                    continue
                if i.get("cover"):
                    target = os.path.join(cdir, "%d.jpg" % bid)
                elif all_images:
                    n += 1
                    os.makedirs(sdir, exist_ok=True)
                    target = os.path.join(sdir, "%d_%d.jpg" % (bid, n))
                else:
                    continue
                with open(target, "wb") as fh:
                    fh.write(data)
                saved += 1
    if all_images:
        for sub, table, key, prefix in (("authors", "AuthorImages", "AuthorID", "a"), ("friends", "FriendImages", "FriendID", "f")):
            d = os.path.join(out_dir, sub)
            os.makedirs(d, exist_ok=True)
            for pid, imgs in group(db.rows(table), key, ("Sorter", "ID") if table == "AuthorImages" else ("ID",)).items():
                for n, i in enumerate(imgs, 1):
                    data = load_image(i.get("image"), folder, prefix, i["ID"])
                    if data:
                        with open(os.path.join(d, "%d_%d.jpg" % (pid, n)), "wb") as fh:
                            fh.write(data)
                        saved += 1
    print("books: %d, authors: %d, loans: %d, pictures saved: %d -> %s" % (
        len(books), len(authors), len(db.rows("LoanHistory")), saved, out_dir))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("database", help="*.amb file")
    ap.add_argument("--out", help="output folder (default: <database>_export)")
    ap.add_argument("--covers", action="store_true", help="save front covers as covers/<id>.jpg")
    ap.add_argument("--all-images", action="store_true", help="also extra pictures, author photos and friend photos")
    a = ap.parse_args()
    export(a.database, a.out or os.path.splitext(os.path.abspath(a.database))[0] + "_export", a.covers, a.all_images)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
