#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clz_tokens.py - dump the token stream of a Collectorz.com desktop database
(Book Collector *.bkc, Movie Collector *.mvc, Music/Game/Comic Collector
files use the same container).

The files are not a database engine: they are a Delphi TWriter-style stream
of tagged values (docs/collectorz.md).  This tool decodes the tags and prints
them one per line with offsets, which is the first step for mapping the
positional record layout of a version you do not know yet.

    python clz_tokens.py MyCollection.bkc > tokens.txt
    python clz_tokens.py MyCollection.mvc --strings      # only strings, quick look

Standard library only; the file is not modified.
"""
import argparse
import datetime
import struct
import sys

# Characters we accept in a UTF-16 string when guessing whether a length
# prefix is followed by text or is just an integer.
def _text_ok(s):
    for c in s:
        o = ord(c)
        if not (32 <= o < 0x250 or 0x370 <= o < 0x530 or 0x2010 <= o <= 0x2030 or 0x3000 <= o < 0xA000
                or 0xAC00 <= o < 0xD7A4 or c in "\r\n\t"):
            return False
    return True


def looks_utf16(b):
    if not b or len(b) % 2:
        return False
    try:
        return _text_ok(b.decode("utf-16-le"))
    except UnicodeDecodeError:
        return False


def tokenize(data, max_str=200000):
    """Return list of (offset, kind, value).

    kinds: END, LIST, INT, STR, EXT (10-byte float, hex), ANSI, DATE, BOOL, RAW.
    Integers are signed (tag 02 = int8, 03 = int16, 04 = int32); a string has
    no tag of its own - it is an integer (length in characters) followed by
    UTF-16LE bytes, so it can only be recognised by looking at what follows.
    """
    pos = 0
    n = len(data)
    toks = []
    while pos < n:
        off = pos
        t = data[pos]
        pos += 1
        if t == 0x00:
            toks.append((off, "END", None))
        elif t == 0x01:
            toks.append((off, "LIST", None))
        elif t in (0x02, 0x03, 0x04):
            size = {2: 1, 3: 2, 4: 4}[t]
            val = int.from_bytes(data[pos:pos + size], "little", signed=True)
            pos += size
            if 0 < val <= max_str and pos + val * 2 <= n and looks_utf16(data[pos:pos + val * 2]):
                s = data[pos:pos + val * 2].decode("utf-16-le")
                pos += val * 2
                # a 1-char "string" that is really two adjacent int tags
                if val == 1 and data[pos - 2] in (0x02, 0x03, 0x04):
                    pos -= 2
                    toks.append((off, "INT", val))
                else:
                    toks.append((off, "STR", s))
            else:
                toks.append((off, "INT", val))
        elif t == 0x05:
            toks.append((off, "EXT", data[pos:pos + 10].hex()))
            pos += 10
        elif t == 0x06:
            ln = data[pos]
            pos += 1
            toks.append((off, "ANSI", data[pos:pos + ln].decode("latin-1")))
            pos += ln
        elif t == 0x08:
            toks.append((off, "BOOL", False))
        elif t == 0x09:
            toks.append((off, "BOOL", True))
        elif t == 0x11:
            d, = struct.unpack_from("<d", data, pos)
            pos += 8
            toks.append((off, "DATE", d))
        else:
            toks.append((off, "RAW", t))
    return toks


def extended_to_float(hex10):
    """80-bit x87 extended -> float (prices); -1.0 means 'not set'."""
    b = bytes.fromhex(hex10)
    mant = int.from_bytes(b[:8], "little")
    se = int.from_bytes(b[8:], "little")
    sign = -1.0 if se & 0x8000 else 1.0
    exp = se & 0x7FFF
    if exp == 0 and mant == 0:
        return 0.0
    return sign * mant * 2.0 ** (exp - 16383 - 63)


def delphi_datetime(d):
    try:
        return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=d)).isoformat(" ", "seconds")
    except (OverflowError, ValueError):
        return repr(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="*.bkc / *.mvc")
    ap.add_argument("--strings", action="store_true", help="print only strings")
    a = ap.parse_args()
    data = open(a.file, "rb").read()
    if not data.startswith(b"\x06\x0eCollectorz.com"):
        sys.exit("not a Collectorz.com desktop database (signature missing)")
    depth = 0
    for off, kind, val in tokenize(data):
        if kind == "END" and depth:
            depth -= 1
        if a.strings:
            if kind == "STR":
                print(val)
            continue
        if kind == "EXT":
            shown = "%s (%g)" % (val, extended_to_float(val))
        elif kind == "DATE":
            shown = "%r (%s)" % (val, delphi_datetime(val))
        elif kind == "STR":
            shown = repr(val)
        else:
            shown = val
        print("%08x %s%s %s" % (off, "  " * depth, kind, "" if shown is None else shown))
        if kind == "LIST":
            depth += 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
