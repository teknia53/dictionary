#!/usr/bin/env python3
"""Merge the old Drupal lexicon into the dictionary table.

Reads tools/drupal_lexicon.json (written by scrape_drupal_lexicon.py), joins on the
GK number, and

  * writes tools/drupal_fields.sql — ALTER TABLE, one UPDATE per existing word, and
        one INSERT per word that exists only in Drupal (words that never occur in the
        NT text, so they were not in the original dictionary data). Run it against D1
        in ~250-statement chunks with `wrangler d1 execute --command` (the --file path
        uses the import API, which this account's token cannot call).
  * applies the same statements to the local SQLite copies given with --sqlite.

Columns added to `dictionary`:
    principal_parts  TEXT   "(ἔλεγον), ἐρῶ, εἶπον or εἶπα, εἴρηκα, εἴρημαι, ἐρρέθην or ἐρρήθην"
    mbg              TEXT   "v-1b(2)" — category in Mounce, The Morphology of Biblical Greek
    dictionary_form  TEXT   "ἀγάπη, -ης, ἡ" — the full lexical entry
    gloss            TEXT   short gloss, HTML with <i>

Idempotent: ALTERs are skipped when the columns exist, UPDATEs rewrite the same values,
and INSERTs are guarded with NOT EXISTS.
"""

import argparse
import html as htmllib
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "drupal_lexicon.json"
OUT = HERE / "drupal_fields.sql"
REPORT = HERE / "drupal_cleanup.txt"

VOWEL = "[αεηιουωἀἁἐἑἠἡἰἱὀὁὐὑὠὡάέήίόύώὰὲὴὶὸὺὼᾳῃῳᾶῆῖῦῶϊϋΐΰ]"
CAP_ROUGH = {"Α": "Ἁ", "Ε": "Ἑ", "Η": "Ἡ", "Ι": "Ἱ", "Ο": "Ὁ", "Υ": "Ὑ", "Ω": "Ὡ"}
CLEANED = []   # (gk, field, before, after) for the report

# Drupal slug → GK number, where the Drupal page carries the wrong number.
GK_FIXES = {
    "saleim": "4887.5",   # Σαλείμ; Drupal says 4887, which is Σαλαμίς
}
# Dictionary forms too garbled to repair by rule.
FORM_FIXES = {
    "georgion": "γεώργιον, ου, τό",   # Drupal: "γεώργιον, ου, τνv"
    # These five Drupal pages have no Greek at all (only transliteration and gloss);
    # the forms below were reconstructed from the transliteration.
    "akoustos": "ἀκουστός, ή, όν",
    "anaprasso": "ἀναπράσσω",
    "aploos": "ἁπλόος, η, ον",
    "athanatos": "ἀθάνατος, ον",
    "deuteron": "δεύτερον",
    "ploos": "πλόος, ου, ὁ",
}


def simplify(s):
    """Same rule as the API's simplifyTranslit: lowercase ASCII letters and digits."""
    s = re.sub(r"<[^>]*>", "", s or "").lower()
    s = unicodedata.normalize("NFD", s)
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


def clean_greek(s, gk="", field=""):
    """Tidy leftovers of the old TekniaGreek font encoding in a Greek string.

    In that font `/` is an iota subscript, `:`/`%` a circumflex, `&` a diaeresis, `v` an
    acute, `\\` smooth+circumflex, `j`/`J` breathings, while English typed in the Greek
    font came out as Greek letters (or → ορ, gen. → γεν., 3rd sg → 3ρδ σγ, and the
    italic tags <e>…</e> → <ε>…</ε> or <Ε&…</Ε&).
    """
    if not s:
        return ""
    before = s
    s = re.sub(r"</?\??[Εε]&?>?", "", s)              # <ε>, </ε>, <?ε>, <Ε&, </Ε&
    s = re.sub(r"\bορ\b", "or", s)
    s = s.replace("γεν.", "gen.")
    s = s.replace("3ρδ σγ", "3rd sg").replace("3ρδ πλ", "3rd pl")
    s = re.sub(rf"({VOWEL})/", "\\1\u0345", s)         # iota subscript
    s = re.sub(rf"({VOWEL})[%:]", "\\1\u0342", s)      # circumflex
    s = re.sub(rf"({VOWEL})&", "\\1\u0308", s)         # diaeresis
    s = re.sub(rf"({VOWEL}[\u0300-\u036f]*)v", "\\1\u0301", s)   # acute
    s = s.replace("\\", "")                            # vowel already carries the marks
    s = re.sub(rf"({VOWEL})[jJ]", "\\1", s)            # redundant breathing code
    s = re.sub(r"!?J([ΑΕΗΙΟΥΩ])", lambda m: CAP_ROUGH[m.group(1)], s)
    s = s.replace(")))", "))")                         # one entry closes more parens than it opens
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+,", ",", s)
    if s != before:
        CLEANED.append((gk, field, before, s))
    return s


def clean_gloss(s, gk=""):
    if not s:
        return ""
    before = s
    s = re.sub(r"</?p>", "", s)
    s = re.sub(r"<(/?)(em|e|ε)>", r"<\1i>", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s != before:
        CLEANED.append((gk, "gloss", before, s))
    return s


def headword(form):
    """ἀγάπη, -ης, ἡ → ἀγάπη"""
    return form.split(",")[0].strip()


def sql_str(s):
    return "'" + s.replace("'", "''") + "'" if s else "NULL"


def gk_key(g):
    return float(g) if re.fullmatch(r"[\d.]+", g) else 0


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

    values = {}     # gk → dict of cleaned fields
    conflicts = 0
    for gk, recs in by_gk.items():
        if len(recs) > 1 and gk in ours:
            # Several Drupal pages claim this GK number (e.g. Salamis and Saleim both say
            # 4887). Keep the ones whose transliteration matches our word.
            same = [(s, r) for s, r in recs if simplify(r.get("transliteration_s")) == ours[gk]]
            recs = same or recs
        fields = {}
        for name, fn in (("pparts", lambda r, s: clean_greek(r.get("pparts", ""), gk, "principal parts")),
                         ("mbg", lambda r, s: (r.get("mbg") or "").strip()),
                         ("dictionary", lambda r, s: FORM_FIXES.get(s) or clean_greek(r.get("dictionary", ""), gk, "dictionary form")),
                         ("gloss", lambda r, s: clean_gloss(r.get("gloss", ""), gk)),
                         ("definition", lambda r, s: (r.get("definition") or "").strip()),
                         ("transliteration", lambda r, s: (r.get("transliteration") or "").strip()),
                         ("strong", lambda r, s: (r.get("strong") or "").strip()),
                         ("frequency", lambda r, s: (r.get("frequency") or "").strip())):
            vals = {fn(r, s) for s, r in recs}
            vals.discard("")
            if len(vals) > 1:
                conflicts += 1
                print(f"  GK {gk}: conflicting {name} across {[s for s, _ in recs]}: {vals}")
            fields[name] = sorted(vals, key=len)[-1] if vals else ""
        fields["slugs"] = [s for s, _ in recs]
        values[gk] = fields

    print(f"{len(data)} Drupal pages → {len(by_gk)} GK numbers, "
          f"{sum(1 for v in values.values() if v['pparts'])} with principal parts, "
          f"{sum(1 for v in values.values() if v['mbg'])} with an MBG tag, "
          f"{sum(1 for v in values.values() if v['dictionary'])} with a dictionary form, "
          f"{sum(1 for v in values.values() if v['gloss'])} with a gloss, {conflicts} conflicts")

    new_words = {}
    if ours:
        missing = sorted(set(ours) - set(values), key=gk_key)
        extra = sorted(set(values) - set(ours), key=gk_key)
        print(f"{len(ours)} words in {Path(check_db).name}: {len(set(ours) & set(values))} matched, "
              f"{len(missing)} without Drupal data, {len(extra)} Drupal-only words to insert")
        if missing:
            print("  no Drupal data for GK:", ", ".join(missing))
        new_words = {gk: values[gk] for gk in extra}
        values = {gk: v for gk, v in values.items() if gk in ours}

    alters = ["ALTER TABLE dictionary ADD COLUMN principal_parts TEXT;",
              "ALTER TABLE dictionary ADD COLUMN mbg TEXT;",
              "ALTER TABLE dictionary ADD COLUMN dictionary_form TEXT;",
              "ALTER TABLE dictionary ADD COLUMN gloss TEXT;"]
    updates = []
    for gk, v in sorted(values.items(), key=lambda kv: gk_key(kv[0])):
        if not any(v[k] for k in ("pparts", "mbg", "dictionary", "gloss")):
            continue
        updates.append(f"UPDATE dictionary SET principal_parts = {sql_str(v['pparts'])}, "
                       f"mbg = {sql_str(v['mbg'])}, dictionary_form = {sql_str(v['dictionary'])}, "
                       f"gloss = {sql_str(v['gloss'])} WHERE gk = {sql_str(gk)};")

    inserts = []
    for gk, v in sorted(new_words.items(), key=lambda kv: gk_key(kv[0])):
        if not v["dictionary"]:
            print(f"  skipping Drupal-only GK {gk} ({v['slugs']}): no dictionary form")
            continue
        strongs = v["strong"] if v["strong"] not in ("", "0") else ""
        freq = v["frequency"] or "0"
        translit = f"<i>{v['transliteration']}</i>" if v["transliteration"] else ""
        definition = v["definition"] or v["gloss"]
        cols = {
            "gk": gk, "strongs": strongs, "lexical": headword(v["dictionary"]),
            "transliteration": translit, "frequency": f"{freq}x", "definition": definition,
            "principal_parts": v["pparts"], "mbg": v["mbg"],
            "dictionary_form": v["dictionary"], "gloss": v["gloss"],
        }
        names = ", ".join(cols)
        vals = ", ".join(sql_str(x) for x in cols.values())
        inserts.append(f"INSERT INTO dictionary ({names}) SELECT {vals} "
                       f"WHERE NOT EXISTS (SELECT 1 FROM dictionary WHERE gk = {sql_str(gk)});")

    OUT.write_text("\n".join(alters + updates + inserts) + "\n", encoding="utf-8")
    print(f"wrote {len(updates)} UPDATEs and {len(inserts)} INSERTs to {OUT}")

    seen = set()
    lines = ["Strings changed while tidying TekniaGreek font leftovers (GK / field: before → after)", ""]
    for gk, field, b, a in sorted(CLEANED, key=lambda t: (gk_key(t[0]), t[1])):
        if (gk, field, b) in seen:
            continue
        if re.sub(r"\s+", " ", unicodedata.normalize("NFC", b)).strip() == a:
            continue    # only Unicode normalisation or whitespace changed
        seen.add((gk, field, b))
        lines.append(f"{gk} {field}: {b}\n      → {a}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(seen)} strings were tidied; see {REPORT.name}")

    for db in args.sqlite:
        con = sqlite3.connect(db)
        cols = {r[1] for r in con.execute("PRAGMA table_info(dictionary)")}
        for stmt in alters:
            col = stmt.split("ADD COLUMN ")[1].split()[0]
            if col not in cols:
                con.execute(stmt)
        for stmt in updates + inserts:
            con.execute(stmt)
        con.commit()
        n = con.execute("SELECT COUNT(*) FROM dictionary WHERE dictionary_form IS NOT NULL").fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM dictionary").fetchone()[0]
        con.close()
        print(f"updated {db}: {n} of {total} rows carry a dictionary form")


if __name__ == "__main__":
    main()
