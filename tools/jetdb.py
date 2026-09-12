# -*- coding: utf-8 -*-
"""
jetdb.py - read Jet 4 (Access 2000 ".mdb" format) database files in pure Python.

All My Movies (*.amm) and All My Books (*.amb) store the collection in a Jet 4
database.  Two things get in the way of reading those files with a generic
parser, and this module takes care of both:

1. Jet page encryption.  Databases created by the programs are opened with the
   OLE DB option ``Jet OLEDB:Encrypt Database=True``.  That is NOT a password:
   every page except the header is RC4-encrypted with a 32-bit key stored in
   the header itself (offset 0x3E, XOR-masked).  We decrypt in memory.

2. Compressed Unicode text.  Jet 4 stores TEXT columns declared ``WITH COMP``
   as UCS-2 with a simple compression: a leading FF FE marker, then runs of
   single bytes (characters U+0000..U+00FF) and, after a 0x00 toggle byte,
   runs of two-byte UTF-16LE code units.  access_parser (the library used
   underneath) ignores the toggle and mangles Cyrillic and other non-Latin
   text, so the text decoder is patched here.

Everything else is delegated to the ``access-parser`` package
(https://pypi.org/project/access-parser/).

Usage::

    from jetdb import JetDatabase
    db = JetDatabase("My Movies.amm")
    print(db.tables)
    for row in db.rows("movies"):
        print(row["Name"], row["year"])

Only reading is supported.  The database file is never modified.
"""
import struct

from access_parser import AccessParser
from access_parser import utils as _ap_utils
import access_parser.access_parser as _ap_main

__all__ = ["JetDatabase", "read_jet_file", "rc4"]

JET_SIGNATURE = b"Standard Jet DB"
# Header bytes 0x3E..0x41 hold the RC4 encoding key XOR-ed with these four
# bytes of the Jet 4 header mask (a database without encryption reads as 0).
JET4_KEY_MASK = bytes.fromhex("fb8abc4e")


def rc4(key, data):
    """Plain RC4, enough for 4 KB pages; no external dependency."""
    S = list(range(256))
    j = 0
    klen = len(key)
    for i in range(256):
        j = (j + S[i] + key[i % klen]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray(len(data))
    i = j = 0
    for n, b in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out[n] = b ^ S[(S[i] + S[j]) & 0xFF]
    return bytes(out)


def jet_encoding_key(header):
    """Return the 32-bit page encryption key of a Jet 4 file (0 = not encrypted)."""
    masked = header[0x3E:0x42]
    return struct.unpack("<I", bytes(a ^ b for a, b in zip(masked, JET4_KEY_MASK)))[0]


def read_jet_file(path):
    """Read a Jet database into memory, decrypting pages if the file is encrypted.

    Returns (data, info) where info is a dict with 'version', 'page_size',
    'encrypted'.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[4:4 + len(JET_SIGNATURE)] != JET_SIGNATURE:
        raise ValueError("not a Jet database (signature 'Standard Jet DB' missing): %s" % path)
    version = data[0x14]
    if version == 0:
        # Jet 3 (Access 97): 2 KB pages, different encryption scheme; the
        # Bolide programs never wrote this format.
        return data, {"version": 3, "page_size": 2048, "encrypted": False}
    page_size = 4096
    key = jet_encoding_key(data)
    if key == 0:
        return data, {"version": 4, "page_size": page_size, "encrypted": False}
    out = bytearray(data)
    for page in range(1, len(data) // page_size):
        start = page * page_size
        page_key = struct.pack("<I", key ^ page)
        out[start:start + page_size] = rc4(page_key, data[start:start + page_size])
    return bytes(out), {"version": 4, "page_size": page_size, "encrypted": True}


def decode_jet4_text(buf):
    """Decode a Jet 4 TEXT value (compressed or plain UCS-2)."""
    if buf[:2] == b"\xff\xfe":
        out = []
        compressed = True
        i = 2
        n = len(buf)
        while i < n:
            b = buf[i]
            if b == 0:
                compressed = not compressed
                i += 1
            elif compressed:
                out.append(chr(b))
                i += 1
            else:
                out.append(buf[i:i + 2].decode("utf-16-le", errors="replace"))
                i += 2
        return "".join(out)
    return buf.decode("utf-16-le", errors="replace")


_orig_parse_type = _ap_utils.parse_type


def _patched_parse_type(data_type, buffer, length=None, version=3, props=None):
    if data_type == _ap_utils.TYPE_TEXT and version > 3:
        return decode_jet4_text(bytes(buffer)).rstrip("\x00")
    return _orig_parse_type(data_type, buffer, length, version, props)


# access_parser imports parse_type by name, so both places must be patched.
_ap_utils.parse_type = _patched_parse_type
_ap_main.parse_type = _patched_parse_type


def _looks_like_text(s):
    return bool(s) and all(ch >= " " or ch in "\r\n\t" for ch in s)


_orig_parse_memo = _ap_main.AccessTable._parse_memo


def _patched_parse_memo(self, relative_obj_data, return_raw=False):
    """Memo columns that were converted from Text by ALTER TABLE keep the old rows
    as plain text without the 12-byte LVAL descriptor (All My Movies did that
    with movies.audioinfo in 2021).  Jet reads them fine; access_parser raises.
    Fall back to decoding the bytes as text when they look like text."""
    try:
        return _orig_parse_memo(self, relative_obj_data, return_raw)
    except Exception:
        raw = bytes(relative_obj_data)
        if return_raw:
            return raw
        text = decode_jet4_text(raw).rstrip("\x00") if self.version > 3 else raw.decode("latin-1")
        if _looks_like_text(text):
            return text
        raise


_ap_main.AccessTable._parse_memo = _patched_parse_memo


class JetDatabase(AccessParser):
    """AccessParser over an in-memory, decrypted copy of the file."""

    def __init__(self, path):
        self.path = path
        self.db_data, self.info = read_jet_file(path)
        self._parse_file_header(self.db_data)
        self._table_defs, self._data_pages, self._all_pages = _ap_utils.categorize_pages(
            self.db_data, self.page_size)
        self._tables_with_data = self._link_tables_to_data()
        self.catalog = self._parse_catalog()
        self.extra_props = self.parse_msys_table()
        self._cache = {}

    @property
    def tables(self):
        return sorted(t for t in self.catalog if not t.startswith("MSys"))

    def real_name(self, name):
        """Table names are case-insensitive in Jet; map to the stored spelling."""
        low = name.lower()
        for t in self.catalog:
            if t.lower() == low:
                return t
        return None

    def has_table(self, name):
        return self.real_name(name) is not None

    def table(self, name):
        """Column-oriented dict {column: [values...]}; {} if the table is missing."""
        real = self.real_name(name)
        if real is None:
            return {}
        if real not in self._cache:
            self._cache[real] = self.parse_table(real) or {}
        return self._cache[real]

    def columns(self, name):
        return list(self.table(name).keys())

    def rows(self, name):
        """Row-oriented list of dicts."""
        cols = self.table(name)
        if not cols:
            return []
        names = list(cols.keys())
        count = len(cols[names[0]])
        return [{c: cols[c][i] for c in names} for i in range(count)]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: jetdb.py <file.amm|file.amb> [table]")
        sys.exit(2)
    db = JetDatabase(sys.argv[1])
    print("Jet %d, page %d, encrypted: %s" % (db.info["version"], db.info["page_size"], db.info["encrypted"]))
    if len(sys.argv) > 2:
        for r in db.rows(sys.argv[2])[:20]:
            print({k: (v if not isinstance(v, (bytes, bytearray)) else "<%d bytes>" % len(v)) for k, v in r.items()})
    else:
        for t in db.tables:
            cols = db.table(t)
            n = len(next(iter(cols.values()))) if cols else 0
            print("%-20s %6d rows  %s" % (t, n, ", ".join(cols.keys())))
