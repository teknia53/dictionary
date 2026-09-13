#!/usr/bin/env python3
"""Add the old Drupal lexicon's principal parts and MBG tag to the dictionary table.

Reads tools/drupal_lexicon.json (written by scrape_drupal_lexicon.py), joins on the
GK number, and

  * writes tools/drupal_fields.sql — ALTER TABLE + one UPDATE per word, ready for
        npx wrangler d1 execute flashworksbible --remote --file=…/drupal_fields.sql
  * applies the same statements to the local SQLite copies given with --sqlite.

Columns added to `dictionary`:
    principal_parts  TEXT   e.g. "(ἔλεγον), ἐρῶ, εἶπον or εἶπα, εἴρηκα, εἴρημαι, ἐρρέθην or ἐρρήθην"
    mbg              TEXT   e.g. "v-1b(2)" — category in Mounce, The Morphology of Biblical Greek

Idempotent: the ALTERs are skipped when the columns exist, and the UPDATEs simply
rewrite the same values.
"""

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "drupal_lexicon.json"
OUT = HERE / "drupal_fields.sql"


VOWEL = "[αεηιουωἀἁἐἑἠἡἰἱὀὁὐὑὠὡάέήίόύώὰὲὴὶὸὺὼᾳῃῳᾶῆῖῦῶ]"
CLEANED = []   # (gk, before, after) for the report

# Drupal slug → GK number, where the Drupal page carries the wrong number.
GK_FIXES = {
    "saleim": "4887.5",   # Σαλείμ; Drupal says 4887, which is Σαλαμίς
}


def simplify(s):
    """Same rule as the API's simplifyTranslit: lowercase ASCII letters and digits."""
    s = re.sub(r"<[^>]*>", "", s or "").lower()
    s = unicodedata.normalize("NFD", s)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


def clean_pparts(s, gk=""):
    """Tidy leftovers of the old TekniaGreek font encoding in the principal parts.

    In that font `/` is an iota subscript, `:`/`%` a circumflex, `\\` smooth+circumflex
    and `j` a smooth breathing, while English typed in the Greek font came out as Greek
    letters (or → ορ, 3rd sg → 3ρδ σγ, <e>…</e> → <ε>…</ε>).
    """
    if not s:
        return ""
    before = s
    s = re.sub(r"<\??ε>", "", s)                       # <ε>ορ</ε> italics wrappers
    s = re.sub(r"</?ε>", "", s)
    s = re.sub(r"\bορ\b", "or", s)
    s = s.replace("3ρδ σγ", "3rd sg").replace("3ρδ πλ", "3rd pl")
    s = re.sub(rf"({VOWEL})/", "\\1\u0345", s)         # iota subscript
    s = re.sub(rf"({VOWEL})[%:]", "\\1\u0342", s)      # circumflex
    s = s.replace("\\", "")                            # vowel already carries the marks
    s = re.sub(rf"({VOWEL})j", "\\1", s)               # redundant breathing code
    s = s.replace(")))", "))")                         # one entry closes more parens than it opens
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+,", ",", s)
    if s != before:
        CLEANED.append((gk, before, s))
    return s


def sql_str(s):
    return "'" + s.replace("'", "''") + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", action="append", default=[],
                    help="local SQLite file(s) to update in place (repeatable)")
    ap.add_argument("--check", metavar="DB",
                    help="SQLite file whose gk list to compare against (defaults to first --sqlite)")
    args = ap.parse_args()

    data = json.loads(SRC.read_text(encoding="utf-8"))
    by_gk = defaultdict(list)
    for slug, rec in data.items():
        if rec.get("status") != 200 or rec.get("type") != "lexicon" or not rec.get("gk"):
            continue
        gk = GK_FIXES.get(slug) or rec["gk"].strip()
        if gk.isdigit():
            gk = str(int(gk))
        by_gk[gk].append((slug, rec))

    # Our own words, for conflict resolution and the coverage report.
    check_db = args.check or (args.sqlite[0] if args.sqlite else None)
    ours = {}
    if check_db:
        con = sqlite3.connect(check_db)
        for gk, translit in con.execute("SELECT gk, transliteration FROM dictionary"):
            gk = str(gk).strip()
            ours[str(int(gk)) if gk.isdigit() else gk] = simplify(translit)
        con.close()

    values = {}
    conflicts = 0
    for gk, recs in by_gk.items():
        if len(recs) > 1 and gk in ours:
            # Several Drupal pages claim this GK number (e.g. Salamis and Saleim both say
            # 4887). Keep the ones whose transliteration matches our word.
            same = [(s, r) for s, r in recs if simplify(r.get("transliteration_s")) == ours[gk]]
            recs = same or recs
        pp = {clean_pparts(r.get("pparts", ""), gk) for _, r in recs}
        mbg = {(r.get("mbg") or "").strip() for _, r in recs}
        pp.discard("")
        mbg.discard("")
        if len(pp) > 1 or len(mbg) > 1:
            conflicts += 1
            print(f"  GK {gk}: conflicting values across {[s for s, _ in recs]}: {pp} {mbg}")
        values[gk] = (sorted(pp, key=len)[-1] if pp else "", sorted(mbg, key=len)[-1] if mbg else "")

    print(f"{len(data)} Drupal pages → {len(by_gk)} GK numbers, "
          f"{sum(1 for p, _ in values.values() if p)} with principal parts, "
          f"{sum(1 for _, m in values.values() if m)} with an MBG tag, {conflicts} conflicts")

    if ours:
        def num(g):
            return float(g) if re.fullmatch(r"[\d.]+", g) else 0
        missing = sorted(set(ours) - set(values), key=num)
        extra = sorted(set(values) - set(ours), key=num)
        print(f"{len(ours)} words in {Path(check_db).name}: {len(set(ours) & set(values))} matched, "
              f"{len(missing)} without Drupal data, {len(extra)} Drupal-only GK numbers")
        if missing:
            print("  no Drupal data for GK:", ", ".join(missing[:60]), "…" if len(missing) > 60 else "")
        if extra:
            print("  Drupal-only GK:", ", ".join(extra[:60]), "…" if len(extra) > 60 else "")
        values = {gk: v for gk, v in values.items() if gk in ours}

    alters = ["ALTER TABLE dictionary ADD COLUMN principal_parts TEXT;",
              "ALTER TABLE dictionary ADD COLUMN mbg TEXT;"]
    updates = []
    for gk, (pp, mbg) in sorted(values.items(), key=lambda kv: float(kv[0])):
        if not pp and not mbg:
            continue
        updates.append(f"UPDATE dictionary SET principal_parts = {sql_str(pp) if pp else 'NULL'}, "
                       f"mbg = {sql_str(mbg) if mbg else 'NULL'} WHERE gk = {sql_str(gk)};")
    OUT.write_text("\n".join(alters + updates) + "\n", encoding="utf-8")
    print(f"wrote {len(updates)} UPDATEs to {OUT}")

    report = HERE / "drupal_pparts_cleanup.txt"
    seen = set()
    lines = ["Principal parts changed while tidying TekniaGreek font leftovers (GK: before → after)", ""]
    for gk, b, a in sorted(CLEANED, key=lambda t: float(t[0]) if re.fullmatch(r"[\d.]+", t[0]) else 0):
        if (gk, b) in seen:
            continue
        seen.add((gk, b))
        lines.append(f"{gk}: {b}\n      → {a}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(seen)} principal-parts strings were tidied; see {report.name}")

    for db in args.sqlite:
        con = sqlite3.connect(db)
        cols = {r[1] for r in con.execute("PRAGMA table_info(dictionary)")}
        for stmt in alters:
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in cols:
                con.execute(stmt)
        for stmt in updates:
            con.execute(stmt)
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM dictionary WHERE mbg IS NOT NULL OR principal_parts IS NOT NULL").fetchone()[0]
        con.close()
        print(f"updated {db}: {n} rows now carry Drupal fields")


if __name__ == "__main__":
    main()
