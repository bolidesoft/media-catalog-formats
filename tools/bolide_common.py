# -*- coding: utf-8 -*-
"""
bolide_common.py - helpers shared by amm_export.py and amb_export.py:
the per-database settings blob, the external image folders, the packed
technical fields and CSV writing.  See docs/allmymovies-amm.md.
"""
import csv
import json
import os
import struct

# ---------------------------------------------------------------- settings blob
# Table `settings`, row Profile='default', column Data.  A sequence of records
# "80-byte header + payload"; both parts are XOR-ed with this key, starting at
# key index -1 (i.e. the first byte of every block is stored as is - a Delphi 6
# off-by-one that became part of the format).
SETTINGS_KEY = b"hDmpSwrdGZxqlHdgfcIRuHsDHs5Tu"
SETTINGS_ID = 0x112
SETTINGS_HDR = 80


def _unxor(buf, shift=1):
    out = bytearray(buf)
    klen = len(SETTINGS_KEY)
    for i in range(shift, len(out)):
        out[i] ^= SETTINGS_KEY[(i - shift) % klen]
    return bytes(out)


def _read_records(blob, hdr_size, shift, wide):
    rows = []
    pos = 0
    while pos + hdr_size <= len(blob):
        hdr = _unxor(blob[pos:pos + hdr_size], shift)
        ident, = struct.unpack_from("<i", hdr, 0)
        if ident != SETTINGS_ID:
            break
        if wide:
            section = hdr[4:76].decode("utf-16-le", "replace").split("\x00", 1)[0]
            key = hdr[76:148].decode("utf-16-le", "replace").split("\x00", 1)[0]
        else:
            section = hdr[4:40].split(b"\x00", 1)[0].decode("latin-1")
            key = hdr[40:76].split(b"\x00", 1)[0].decode("latin-1")
        size, = struct.unpack_from("<i", hdr, hdr_size - 4)
        pos += hdr_size
        rows.append((section, key, _unxor(blob[pos:pos + size], shift)))
        pos += size
    return rows


def parse_settings_blob(blob, ansi="cp1252"):
    """Return a list of (section, key, raw_bytes) and a dict of decoded values.

    Values have no type tag: 1 byte = boolean, 4 bytes = integer, anything
    else = string (UTF-8 when [meta] strenc >= 2, otherwise the ANSI code
    page of the machine that wrote it).
    """
    rows = _read_records(blob, SETTINGS_HDR, 1, False)
    if not rows:
        # Variant written by some 2026 builds: section/key as UTF-16 (152-byte
        # header) and the XOR key applied without the one-byte shift.
        rows = _read_records(blob, 152, 0, True)
    utf8 = any(s.lower() == "meta" and k.lower() == "strenc" and len(v) == 4 and struct.unpack("<i", v)[0] >= 2
               for s, k, v in rows)
    values = {}
    for section, key, raw in rows:
        if len(raw) == 1:
            val = bool(raw[0])
        elif len(raw) == 4:
            val = struct.unpack("<i", raw)[0]
        elif len(raw) == 8 and key.lower().endswith(("date", "time")):
            # Delphi TDateTime: days since 1899-12-30 as a double
            days = struct.unpack("<d", raw)[0]
            val = delphi_date(days) if 0 < days < 200000 else ""
        else:
            try:
                val = raw.decode("utf-8") if utf8 else raw.decode(ansi)
            except UnicodeDecodeError:
                val = raw.decode(ansi, errors="replace")
            val = val.rstrip("\x00").lstrip("﻿")
        values["%s/%s" % (section.lower(), key.lower())] = val
    return rows, values


def delphi_date(days):
    import datetime
    try:
        return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=days)).isoformat(" ", "seconds")
    except (OverflowError, ValueError):
        return ""


def clean_date(s):
    """Jet DateTime as text; the program writes 0 (= 1899-12-30) for 'no date'."""
    s = (s or "")
    if isinstance(s, str) and (s.startswith("1899") or s.startswith("1900-01-0")):
        return ""
    return s


def setting(settings, section, key, default=None):
    return settings.get("%s/%s" % (section.lower(), key.lower()), default)


def database_settings(db):
    """Settings of the default profile as a dict, {} if the table is empty."""
    for row in db.rows("settings"):
        if (row.get("Profile") or "").lower() == "default" and row.get("Data"):
            return parse_settings_blob(bytes(row["Data"]))[1]
    return {}


# ---------------------------------------------------------------- image files
def images_folder(db_path):
    """<folder>\\<name>_images2 - where pictures live when they are not stored in the database."""
    base, _ = os.path.splitext(os.path.abspath(db_path))
    return base + "_images2"


def image_file(folder, prefix, image_id):
    """Pictures are spread over 100 subfolders by id: _images2\\NN\\<prefix><id>.jpg"""
    return os.path.join(folder, "%02d" % (image_id % 100), "%s%d.jpg" % (prefix, image_id))


def load_image(blob, folder, prefix, image_id):
    """Bytes of a picture: from the blob if present, else from the external file."""
    if blob:
        return bytes(blob)
    path = image_file(folder, prefix, image_id)
    if os.path.isfile(path):
        with open(path, "rb") as f:
            return f.read()
    return None


# ---------------------------------------------------------------- packed fields
def split_video_info(s):
    """movies.videoinfo = codec ~ frame rate ~ bit depth ~ bitrate ~ stream count"""
    parts = [(p or "").strip() for p in (s or "").split("~")] + [""] * 5
    return {"video_codec": parts[0], "frame_rate": parts[1], "bit_depth": parts[2],
            "video_bitrate": parts[3], "video_streams": parts[4]}


def audio_tracks(s):
    """movies.audioinfo in any of its three historical layouts -> list of dicts."""
    s = (s or "").strip()
    if not s:
        return []
    if s.startswith("{"):
        try:
            data = json.loads(s)
        except ValueError:
            return []
        out = []
        for t in data.get("i", []):
            out.append({"language": t.get("l", ""), "codec": t.get("c", ""), "bitrate": t.get("b", ""),
                        "channels": t.get("h", ""), "sample_rate": t.get("s", "")})
        return out
    parts = s.split("~") + ["", "", ""]
    codecs = [c.strip() for c in parts[0].split(",")]
    bitrates = [b.strip() for b in parts[1].split(",")]
    langs = [l.strip() for l in parts[2].split(",")]
    out = []
    for i in range(max(len(codecs), len(langs))):
        out.append({"language": langs[i] if i < len(langs) else "",
                    "codec": codecs[i] if i < len(codecs) else "",
                    "bitrate": bitrates[i] if i < len(bitrates) else "",
                    "channels": "", "sample_rate": ""})
    return [t for t in out if any(t.values())]


def audio_summary(tracks):
    out = []
    for t in tracks:
        s = "%s %s %s" % (t["language"], t["codec"], t["bitrate"])
        if t["channels"]:
            s += " %sch" % t["channels"]
        out.append(" ".join(s.split()))
    return out


def money(v):
    try:
        return "" if not v else round(float(v), 2)
    except (TypeError, ValueError):
        return ""


def tenth(v):
    """Ratings are stored x10 (86 = 8.6)."""
    try:
        return "" if v in (None, 0) else int(v) / 10.0
    except (TypeError, ValueError):
        return ""


# ---------------------------------------------------------------- output
def write_csv(path, rows):
    if not rows:
        return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            flat = {}
            for k, v in r.items():
                if isinstance(v, list):
                    flat[k] = "; ".join(str(x) for x in v)
                elif isinstance(v, dict):
                    flat[k] = "; ".join("%s=%s" % kv for kv in v.items())
                elif v is None:
                    flat[k] = ""
                else:
                    flat[k] = v
            w.writerow(flat)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, default=str)


def by_id(rows, key):
    return {r[key]: r for r in rows}


def group(rows, key, sort_keys=("Sorter", "ID")):
    """Link rows grouped by a foreign key, in the order the program shows them."""
    out = {}
    for r in rows:
        out.setdefault(r.get(key), []).append(r)
    for k in out:
        out[k].sort(key=lambda r: tuple((r.get(s) if r.get(s) is not None else -1) for s in sort_keys))
    return out


def save_settings_report(path, settings):
    """Write the settings that matter for a migration; never the write password itself."""
    with open(path, "w", encoding="utf-8") as fh:
        for k in sorted(settings):
            v = settings[k]
            if k.lower().endswith("/writepass"):
                v = "(set)" if v else "(empty)"
            fh.write("%s = %r\n" % (k, v))
