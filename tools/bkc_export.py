#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bkc_export.py - export a Collectorz.com Book Collector desktop database
(*.bkc, schema 340 = Book Collector 23.x, the last Windows version) to CSV
and JSON, and find the cover files that go with it.

    python bkc_export.py "Documents\\Book Collector\\MyCollection.bkc"
    python bkc_export.py MyCollection.bkc --out export --covers

The .bkc holds no images, only absolute paths from the machine it was made
on; covers are looked up by file name in Images\\ next to the .bkc (the
default layout of Book Collector's data folder).

Fields are located by anchors in the token stream, not by fixed offsets
(docs/collectorz.md), so an unknown version yields empty fields rather than
garbage.  Standard library only.  Exports title, subtitle, ISBN, authors and
other credits, plot, added date, cover and thumbnail paths, price, plus the
lookup names referenced by id where the position is stable (publisher,
format, genres/subjects are not yet mapped - contributions welcome).
"""
import argparse
import csv
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clz_tokens import tokenize, extended_to_float  # noqa: E402

ROLES = {12: "author", 13: "editor", 14: "translator", 15: "illustrator", 16: "photographer",
         17: "narrator", 18: "cover artist", 19: "foreword"}   # 12 verified; others by observation


def read_bkc(path):
    data = open(path, "rb").read()
    if not data.startswith(b"\x06\x0eCollectorz.com"):
        sys.exit("not a Collectorz.com database: %s" % path)
    toks = tokenize(data)
    header = {"collection_type": toks[1][2] if toks[1][1] == "ANSI" else "", "schema": toks[2][2], "app_version": toks[3][2]}

    # lookup entries: INT id, 0, 0, 0, TRUE, 0, STR name  (ids are global)
    names = {}
    for i in range(len(toks) - 6):
        if (toks[i][1] == "INT" and toks[i + 1][1] == "INT" and toks[i + 1][2] == 0
                and toks[i + 2][1] == "INT" and toks[i + 2][2] == 0
                and toks[i + 3][1] == "INT" and toks[i + 3][2] == 0
                and toks[i + 4][1] == "BOOL" and toks[i + 4][2] is True
                and toks[i + 5][1] == "INT" and toks[i + 5][2] == 0
                and toks[i + 6][1] == "STR"):
            names.setdefault(toks[i][2], toks[i + 6][2])

    # book records: INT id, INT ordinal, STR "{GUID}"
    guid_re = re.compile(r"^\{[0-9A-F-]{36}\}$")
    starts = [i - 2 for i, t in enumerate(toks)
              if t[1] == "STR" and guid_re.match(str(t[2])) and i >= 2 and toks[i - 2][1] == "INT" and toks[i - 1][1] == "INT"]
    starts = [s for s in starts if toks[s][2] > 0 and 0 < toks[s + 1][2] <= toks[s][2]]

    books = []
    for bi, start in enumerate(starts):
        end = starts[bi + 1] if bi + 1 < len(starts) else len(toks)
        seg = toks[start:end]
        b = {"id": seg[0][2], "guid": seg[2][2], "title": "", "subtitle": "", "plot": "", "isbn": "",
             "cover": "", "thumbnail": "", "added": "", "price": "", "credits": []}
        for j, t in enumerate(seg):
            if t[1] != "STR":
                continue
            s = t[2]
            if "\\Images\\" in s and not b["cover"]:
                b["cover"] = s
            elif "\\Thumbnails\\" in s and not b["thumbnail"]:
                b["thumbnail"] = s
                # after the thumbnail: INT16, 0, 0, 0, TRUE, 0, STR title, 0, 0, subtitle, plot
                # (an empty string is written as a bare length 0, i.e. it tokenizes as INT 0)
                k = j + 1
                while k < len(seg) and seg[k][1] != "STR":
                    k += 1
                if k < len(seg):
                    b["title"] = seg[k][2]
                    if k + 3 < len(seg) and seg[k + 3][1] == "STR":
                        b["subtitle"] = seg[k + 3][2]
                    if k + 4 < len(seg) and seg[k + 4][1] == "STR":
                        b["plot"] = seg[k + 4][2]
            elif re.match(r"^\d{13}$|^\d{9}[\dX]$", s) and not b["isbn"]:
                b["isbn"] = s
        dates = [t[2] for t in seg if t[1] == "DATE"]
        if dates:
            b["added"] = (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=dates[0])).isoformat(" ", "seconds")
        exts = [extended_to_float(t[2]) for t in seg if t[1] == "EXT"]
        if exts and exts[0] >= 0:
            b["price"] = exts[0]
        # credits: INT creditId, 0, 0, 0, TRUE, 0, INT role, INT personId, INT -1 (no character)
        for j in range(len(seg) - 8):
            if (seg[j][1] == "INT" and seg[j + 1][1] == "INT" and seg[j + 1][2] == 0 and seg[j + 2][2] == 0
                    and seg[j + 3][2] == 0 and seg[j + 4][1] == "BOOL" and seg[j + 4][2] is True and seg[j + 5][2] == 0
                    and seg[j + 6][1] == "INT" and seg[j + 7][1] == "INT" and seg[j + 8][1] == "INT" and seg[j + 8][2] == -1
                    and seg[j + 7][2] in names):
                b["credits"].append({"role": ROLES.get(seg[j + 6][2], "role%d" % seg[j + 6][2]), "person": names[seg[j + 7][2]]})
        b["authors"] = [c["person"] for c in b["credits"] if c["role"] == "author"]
        b["other_credits"] = ["%s (%s)" % (c["person"], c["role"]) for c in b["credits"] if c["role"] != "author"]
        books.append(b)
    return header, books, names


def find_cover(bkc_path, cover_path):
    """The stored path is absolute for another machine; match by file name next to the .bkc."""
    if not cover_path:
        return ""
    name = cover_path.replace("\\", "/").rsplit("/", 1)[-1]
    for sub in ("Images", os.path.join("Data", "Images"), "."):
        cand = os.path.join(os.path.dirname(os.path.abspath(bkc_path)), sub, name)
        if os.path.isfile(cand):
            return cand
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="*.bkc")
    ap.add_argument("--out", help="output folder (default: <file>_export)")
    ap.add_argument("--covers", action="store_true", help="copy covers found next to the .bkc into covers/")
    a = ap.parse_args()
    out = a.out or os.path.splitext(os.path.abspath(a.file))[0] + "_export"
    header, books, names = read_bkc(a.file)
    os.makedirs(out, exist_ok=True)
    rows = []
    copied = 0
    for b in books:
        local = find_cover(a.file, b["cover"])
        if a.covers and local:
            cdir = os.path.join(out, "covers")
            os.makedirs(cdir, exist_ok=True)
            target = os.path.join(cdir, "%d%s" % (b["id"], os.path.splitext(local)[1]))
            with open(local, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())
            copied += 1
        rows.append({"id": b["id"], "title": b["title"], "subtitle": b["subtitle"], "authors": "; ".join(b["authors"]),
                     "other_credits": "; ".join(b["other_credits"]), "isbn": b["isbn"], "plot": b["plot"],
                     "price": b["price"], "added": b["added"], "cover_original_path": b["cover"], "cover_file": local})
    with open(os.path.join(out, "books.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, "books.json"), "w", encoding="utf-8") as fh:
        json.dump({"header": header, "books": books}, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(out, "lookup_names.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "name"])
        for k in sorted(names):
            w.writerow([k, names[k]])
    print("%s schema %s (app %s): %d books, %d lookup names, covers copied: %d -> %s" % (
        header["collection_type"], header["schema"], header["app_version"], len(books), len(names), copied, out))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
