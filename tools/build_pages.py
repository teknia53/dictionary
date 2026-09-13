#!/usr/bin/env python3
"""Build the static letter-index pages and sitemap for the Greek NT Dictionary.

Reads every entry from the live API (one browse request per Greek letter) and writes:

    site/words/index.html      all 24 letters with word counts
    site/words/<letter>.html   every word for that letter, linking to its entry
    site/sitemap.xml           home, letter pages, and every entry URL

Entry URLs use the simplified transliteration as the slug (/dictionary/agapao),
which matches the old /greek-dictionary/<word> pages. The few entries that share
a transliteration link by GK number instead (/dictionary/gk:726) so each link
lands on exactly one entry.

Usage:  python3 tools/build_pages.py
Then deploy with:  npx wrangler pages deploy site --project-name=greek-dictionary --branch=main --commit-dirty=true
"""

import html
import json
import re
import subprocess
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path

import site_header  # tools/site_header.py — the shared BillMounce.com header

API_BASE = "https://flashworksbible-api.bill-mounce.workers.dev"
SITE_HOST = "https://www.billmounce.com"
DICT_PATH = "/greek-dictionary"
ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
WORDS_DIR = SITE_DIR / "words"

# (lowercase greek, uppercase greek, english name)
LETTERS = [
    ("α", "Α", "alpha"), ("β", "Β", "beta"), ("γ", "Γ", "gamma"), ("δ", "Δ", "delta"),
    ("ε", "Ε", "epsilon"), ("ζ", "Ζ", "zeta"), ("η", "Η", "eta"), ("θ", "Θ", "theta"),
    ("ι", "Ι", "iota"), ("κ", "Κ", "kappa"), ("λ", "Λ", "lambda"), ("μ", "Μ", "mu"),
    ("ν", "Ν", "nu"), ("ξ", "Ξ", "xi"), ("ο", "Ο", "omicron"), ("π", "Π", "pi"),
    ("ρ", "Ρ", "rho"), ("σ", "Σ", "sigma"), ("τ", "Τ", "tau"), ("υ", "Υ", "upsilon"),
    ("φ", "Φ", "phi"), ("χ", "Χ", "chi"), ("ψ", "Ψ", "psi"), ("ω", "Ω", "omega"),
]
GREEK_ORDER = {lower: i for i, (lower, _, _) in enumerate(LETTERS)}


# ---------------------------------------------------------------- data helpers

def strip_tags(s):
    return re.sub(r"<[^>]*>", "", s or "")


def strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))


def simplify_translit(s):
    """Same rule as simplifyTranslit() in the API Worker: lowercase, no diacritics, a-z0-9 only."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(strip_tags(s).lower()))


def greek_sort_key(lexical):
    base = strip_accents(strip_tags(lexical)).lower().replace("ς", "σ")
    return [GREEK_ORDER.get(ch, 99) for ch in base]


def gk_sort_key(gk):
    try:
        return float(gk)
    except ValueError:
        return 0.0


def fetch_letter(letter):
    out = subprocess.run(
        ["curl", "-sf", "-G", f"{API_BASE}/api/dict/browse", "--data-urlencode", f"letter={letter}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def short_gloss(definition, limit=90):
    text = html.unescape(strip_tags(definition)).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


# ---------------------------------------------------------------- page template

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Georgia, 'Times New Roman', serif; background: #F7F3E9; color: #333; min-height: 100vh; }
.app-title { background: #005a96; color: white; padding: 18px 20px 16px; text-align: center; }
.app-title h1 { font-size: 28px; font-weight: normal; letter-spacing: 1px; }
.app-title h1 a { color: white; text-decoration: none; }
main { max-width: 900px; margin: 0 auto 40px; padding: 0 20px; }
.search-container { max-width: 700px; margin: 30px auto 0; }
.search-box { display: flex; gap: 10px; }
.search-box input { flex: 1; padding: 12px 16px; font-size: 18px; font-family: 'Times New Roman', Times, serif; border: 2px solid #ccc; border-radius: 6px; outline: none; }
.search-box input:focus { border-color: #0067ac; }
.search-box button { padding: 12px 24px; font-size: 16px; background: #0067ac; color: white; border: none; border-radius: 6px; cursor: pointer; font-family: Georgia, 'Times New Roman', serif; }
.search-box button:hover { background: #005490; }
.search-hint { margin-top: 8px; font-size: 14px; color: #888; }
.letter-nav { margin: 12px 0 24px; font-size: 14px; color: #888; line-height: 2; text-align: center; }
.letter-nav a { display: inline-block; min-width: 26px; text-align: center; margin: 0 1px; color: #0067ac; text-decoration: none; font-family: 'Times New Roman', Times, serif; font-size: 18px; }
.letter-nav a:hover { text-decoration: underline; }
.letter-nav a.current { background: #0067ac; color: white; border-radius: 4px; }
.letter-nav a.all { font-family: Georgia, 'Times New Roman', serif; font-size: 14px; margin-left: 8px; }
h2.letter-heading { font-size: 24px; font-weight: bold; color: #0067ac; margin-bottom: 6px; font-family: 'Times New Roman', Times, serif; }
p.intro { color: #666; font-size: 15px; margin-bottom: 16px; line-height: 1.5; }
p.intro a { color: #0067ac; }
.letter-table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.letter-table thead { background: #0067ac; color: white; }
.letter-table th { padding: 10px 12px; text-align: left; font-size: 14px; font-weight: normal; }
.letter-table td { padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 15px; vertical-align: top; }
.letter-table tr:hover { background: #eef5fb; }
.letter-table .lex { font-family: 'Times New Roman', Times, serif; font-size: 18px; white-space: nowrap; }
.letter-table .short-def { color: #555; font-size: 14px; }
.letter-table a { color: #0067ac; text-decoration: none; }
.letter-table a:hover { text-decoration: underline; }
.pager { display: flex; justify-content: space-between; margin: 20px 0; font-size: 16px; }
.pager a { color: #0067ac; text-decoration: none; }
.pager a:hover { text-decoration: underline; }
.index-list { list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.index-list li a { display: flex; justify-content: space-between; align-items: baseline; background: white; padding: 12px 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); color: #0067ac; text-decoration: none; }
.index-list li a:hover { background: #eef5fb; }
.index-list .g { font-family: 'Times New Roman', Times, serif; font-size: 22px; }
.index-list .n { font-size: 13px; color: #888; }
@media (max-width: 600px) {
  .app-title h1 { font-size: 22px; }
  .letter-table th:nth-child(5), .letter-table td:nth-child(5) { display: none; }
  .letter-table td, .letter-table th { padding: 6px 8px; font-size: 13px; }
  .letter-table .lex { font-size: 16px; }
}
"""


SITE_HEADER_HEAD = site_header.head_html()
SITE_HEADER_BODY = site_header.body_html()


def page(title, description, canonical_path, body):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)}</title>
    <meta name="description" content="{html.escape(description)}">
    <link rel="canonical" href="{SITE_HOST}{canonical_path}">
    <style>{CSS}</style>
    {SITE_HEADER_HEAD}
</head>
<body>
    {SITE_HEADER_BODY}
    <div class="app-title">
        <h1><a href="{DICT_PATH}/">Greek New Testament Dictionary</a></h1>
    </div>
    <main>
{body}
    </main>
</body>
</html>
"""


def search_box():
    """The same search box as the app; submits to the app home page as ?q=…"""
    return f"""<div class="search-container">
            <form class="search-box" action="{DICT_PATH}/" method="get">
                <input type="text" name="q" placeholder="Search by GK number, Strong's number, or Greek word..." autocomplete="off">
                <button type="submit">Search</button>
            </form>
            <div class="search-hint">Examples: gk:27, s:26 (Strong's), ἀγαπάω (Greek word), logos (English transliteration), or just a number to search on the GK number</div>
        </div>"""


def letter_nav(current=None):
    links = []
    for lower, upper, name in LETTERS:
        cls = ' class="current"' if name == current else ""
        links.append(f'<a href="{DICT_PATH}/words/{name}"{cls} title="{name}">{upper}</a>')
    links.append(f'<a href="{DICT_PATH}/words/" class="all">Index</a>')
    return '<nav class="letter-nav" aria-label="Browse by letter"><span>Browse by letter:</span> ' + "".join(links) + "</nav>"


# ---------------------------------------------------------------- build

def main():
    WORDS_DIR.mkdir(parents=True, exist_ok=True)

    by_letter = {}
    for lower, _, name in LETTERS:
        words = fetch_letter(lower)
        words.sort(key=lambda w: (greek_sort_key(w["lexical"]), gk_sort_key(w["gk"])))
        by_letter[name] = words
        print(f"{name:8s} {len(words):4d} words")

    all_words = [w for words in by_letter.values() for w in words]
    translit_counts = Counter(simplify_translit(w["transliteration"]) for w in all_words)

    def slug_for(w):
        s = simplify_translit(w["transliteration"])
        if s and translit_counts[s] == 1:
            return s
        return f"gk:{w['gk']}"

    entry_urls = []
    shared = 0

    for i, (lower, upper, name) in enumerate(LETTERS):
        words = by_letter[name]
        rows = []
        for w in words:
            slug = slug_for(w)
            if slug.startswith("gk:"):
                shared += 1
            href = f"{DICT_PATH}/{slug}"
            entry_urls.append(href)
            lex = html.escape(strip_tags(w["lexical"]))
            translit = html.escape(strip_tags(w["transliteration"]))
            gk = html.escape(str(w["gk"]))
            strongs = html.escape(str(w["strongs"])) if w.get("strongs") else "—"
            gloss = html.escape(short_gloss(w.get("definition")))
            rows.append(
                f'<tr><td class="lex"><a href="{href}">{lex}</a></td>'
                f'<td><a href="{href}">{translit}</a></td>'
                f"<td>{gk}</td><td>{strongs}</td>"
                f'<td class="short-def">{gloss}</td></tr>'
            )

        prev_ = LETTERS[i - 1] if i > 0 else None
        next_ = LETTERS[i + 1] if i < len(LETTERS) - 1 else None
        pager = '<div class="pager">'
        pager += f'<a href="{DICT_PATH}/words/{prev_[2]}">← {prev_[1]} {prev_[2]}</a>' if prev_ else "<span></span>"
        pager += f'<a href="{DICT_PATH}/words/{next_[2]}">{next_[1]} {next_[2]} →</a>' if next_ else "<span></span>"
        pager += "</div>"

        body = f"""{search_box()}
        {letter_nav(name)}
        <h2 class="letter-heading">{upper} {lower} — {name} — {len(words)} words</h2>
        <p class="intro">Every Greek word in the New Testament beginning with {name} ({upper}), from Bill Mounce's
        <a href="{DICT_PATH}/">Greek New Testament Dictionary</a>. Click a word for its full definition,
        GK and Strong's numbers, frequency, and every New Testament occurrence.</p>
        <table class="letter-table">
            <thead><tr><th>Greek</th><th>Transliteration</th><th>GK</th><th>Strong's</th><th>Definition</th></tr></thead>
            <tbody>
                {chr(10).join(rows)}
            </tbody>
        </table>
        {pager}
        {letter_nav(name)}"""

        title = f"Greek Words Beginning with {name.capitalize()} ({upper}) – Greek New Testament Dictionary"
        description = (f"All {len(words)} Greek New Testament words beginning with {name} ({upper}), "
                       f"with transliteration, GK and Strong's numbers, and definitions from Bill Mounce's dictionary.")
        (WORDS_DIR / f"{name}.html").write_text(
            page(title, description, f"{DICT_PATH}/words/{name}", body), encoding="utf-8")

    # Index of letters
    items = "".join(
        f'<li><a href="{DICT_PATH}/words/{name}"><span class="g">{upper} {lower} <small>{name}</small></span>'
        f'<span class="n">{len(by_letter[name])} words</span></a></li>'
        for lower, upper, name in LETTERS
    )
    body = f"""{search_box()}
        {letter_nav()}
        <h2 class="letter-heading">All Greek New Testament Words by Letter</h2>
        <p class="intro">{len(all_words)} words from Bill Mounce's <a href="{DICT_PATH}/">Greek New Testament Dictionary</a>,
        arranged by their first letter. Each entry gives the definition, GK and Strong's numbers, frequency,
        and every occurrence in the New Testament.</p>
        <ul class="index-list">{items}</ul>"""
    (WORDS_DIR / "index.html").write_text(
        page("Browse All Greek New Testament Words – Greek New Testament Dictionary",
             f"Browse all {len(all_words)} words in Bill Mounce's Greek New Testament Dictionary by letter, from alpha to omega.",
             f"{DICT_PATH}/words/", body), encoding="utf-8")

    # Sitemap
    today = date.today().isoformat()
    urls = [f"{DICT_PATH}/", f"{DICT_PATH}/words/"] + [f"{DICT_PATH}/words/{name}" for _, _, name in LETTERS] + entry_urls
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append(f"  <url><loc>{html.escape(SITE_HOST + u)}</loc><lastmod>{today}</lastmod></url>")
    lines.append("</urlset>")
    (SITE_DIR / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n{len(all_words)} entries, {shared} linked by GK number (shared transliteration)")
    print(f"wrote {len(LETTERS)} letter pages + index to {WORDS_DIR}")
    print(f"wrote sitemap with {len(urls)} URLs to {SITE_DIR / 'sitemap.xml'}")


if __name__ == "__main__":
    main()
