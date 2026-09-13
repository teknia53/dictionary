#!/usr/bin/env python3
"""Repair garbled headwords in the dictionary table.

The original dictionary data (dictionary.csv → dictionary.lexical) went through a font
conversion that mangled 691 headwords: τη → θ (ἁγιόθς for ἁγιότης), αι → ἅ (ἀναβἅνω
for ἀναβαίνω), ώ → ῶ (Ἀαρῶν for Ἀαρών), αἱ → αἰ. The old Drupal lexicon's dictionary
form ("ἁγιότης, ητος, ἡ") is correct, so wherever our headword differs from the Drupal
form's headword we take the Drupal one.

Writes tools/headword_fixes.sql (one UPDATE per word; run against D1 in chunks with
`wrangler d1 execute --command`) and applies it to the SQLite files given with --sqlite.
"""

import argparse
import sqlite3
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "headword_fixes.sql"


def headword(form):
    return unicodedata.normalize("NFC", form.split(",")[0].strip())


def sql_str(s):
    return "'" + s.replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", action="append", default=[], help="SQLite file(s) to fix in place")
    ap.add_argument("--source", default=str(HERE.parent / "dictionary.dat"),
                    help="SQLite file to read gk/lexical/dictionary_form from")
    args = ap.parse_args()

    con = sqlite3.connect(args.source)
    rows = con.execute("SELECT gk, lexical, dictionary_form FROM dictionary "
                       "WHERE dictionary_form IS NOT NULL AND dictionary_form <> ''").fetchall()
    con.close()

    updates = []
    for gk, lexical, form in rows:
        good = headword(form)
        if unicodedata.normalize("NFC", lexical or "") != good:
            updates.append(f"UPDATE dictionary SET lexical = {sql_str(good)} WHERE gk = {sql_str(str(gk))};")
    OUT.write_text("\n".join(updates) + "\n", encoding="utf-8")
    print(f"{len(updates)} headwords to fix; wrote {OUT}")

    for db in args.sqlite:
        con = sqlite3.connect(db)
        for stmt in updates:
            con.execute(stmt)
        con.commit()
        con.close()
        print(f"applied to {db}")


if __name__ == "__main__":
    main()
