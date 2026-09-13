#!/usr/bin/env python3
"""Scrape the old Drupal "lexicon" nodes on www.billmounce.com.

The dictionary-proxy Worker owns /greek-dictionary/* on Cloudflare, so the Drupal
node pages are reached through an encoded slash (/greek-dictionary%2F<slug>), which
misses the Worker route but which Drupal decodes to the normal path alias.

Steps
  1. Read the 24 letter TOC pages (/greek-dictionary/toc/<letter>) for the entry slugs.
  2. Fetch every node page and pull out its fields:
       field-lexical-dictionary        full dictionary form  (ἀγάπη, -ης, ἡ)
       field-lexicon-transliteration   agapē
       field-lexicon-transliteration-s agape
       field-lexicon-pparts            principal parts (verbs only)
       field-lexicon-strong            Strong's number
       field-lexicon-gk                GK number  (join key for our D1 table)
       field-lexicon-frequency
       field-lexicon-mbg               Morphology of Biblical Greek tag  (n-1b, v-1b(2))
       field-lexicon-gloss             short gloss (HTML)
  3. Write tools/drupal_lexicon.json  { slug: {nid, fields...} }.

Resumable: entries already in the JSON are skipped. Run with --letters alpha,beta to
limit the scope while testing.
"""

import argparse
import concurrent.futures as cf
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.billmounce.com"
LETTERS = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
           "omicron pi rho sigma tau upsilon phi chi psi omega").split()
OUT = Path(__file__).resolve().parent / "drupal_lexicon.json"
UA = "Mozilla/5.0 (compatible; billmounce-dictionary-migration; bill@teknia.com)"

FIELD_RE = re.compile(
    r'<div class="[^"]*field--name-(field-[a-z-]+|body)[^"]*"[^>]*>(.*?)</div>\s*</div>',
    re.S)
ITEM_RE = re.compile(r'<div class="field__item">(.*?)$', re.S)


def fetch(path, tries=4):
    """GET a Drupal path (given unencoded, e.g. greek-dictionary/agape)."""
    url = BASE + "/" + urllib.parse.quote(path, safe="")
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
                if "x-generator" not in {k.lower() for k in r.headers.keys()}:
                    raise RuntimeError("response did not come from Drupal (Worker answered?)")
                return r.status, body
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):      # 403 = unpublished node (anonymous visitor)
                return e.code, ""
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{path}: {last}")


def toc_slugs(letter):
    status, body = fetch(f"greek-dictionary/toc/{letter}")
    if status != 200:
        raise RuntimeError(f"TOC {letter} returned {status}")
    slugs = re.findall(r'href="/greek-dictionary/([^"/?#]+)"', body)
    return sorted(set(html.unescape(s) for s in slugs))


def parse_node(body):
    """Return {field_name: text} for the lexicon fields, plus nid / type."""
    out = {}
    m = re.search(r'rel="shortlink" href="[^"]*/node/(\d+)"', body)
    if m:
        out["nid"] = int(m.group(1))
    m = re.search(r'node--type-([a-z_-]+)', body)
    out["type"] = m.group(1) if m else None
    main = re.search(r"<main.*?</main>", body, re.S)
    scope = main.group(0) if main else body
    # Walk the field wrappers one at a time (regex nesting is unreliable, so find each
    # wrapper start and take everything up to the next wrapper start).
    starts = [(mm.start(), mm.group(1)) for mm in
              re.finditer(r'<div class="[^"]*\bfield--name-(field-lexic[a-z-]+)', scope)]
    for i, (pos, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(scope)
        chunk = scope[pos:end]
        im = re.search(r'<div class="field__item">(.*)', chunk, re.S)
        if not im:
            continue
        val = im.group(1)
        # cut at the wrapper's closing divs
        val = re.split(r'</div>\s*</div>', val, maxsplit=1)[0]
        val = val.strip()
        key = name.replace("field-lexicon-", "").replace("field-lexical-", "").replace("-", "_")
        if name == "field-lexicon-gloss":
            out[key] = re.sub(r"\s+", " ", val)
        else:
            out[key] = html.unescape(re.sub(r"<[^>]+>", "", val)).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--letters", help="comma-separated subset of TOC letters")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="stop after N new entries (testing)")
    ap.add_argument("--slugs", help="comma-separated slugs to fetch instead of reading the TOC pages "
                    "(e.g. hagnos-0: Drupal's de-duplicated alias for the adverb ἁγνῶς, "
                    "which the TOC page links to the adjective's slug)")
    args = ap.parse_args()

    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    letters = args.letters.split(",") if args.letters else LETTERS

    slugs = []
    if args.slugs:
        slugs = args.slugs.split(",")
    else:
        for letter in letters:
            s = toc_slugs(letter)
            print(f"TOC {letter}: {len(s)} slugs", flush=True)
            slugs.extend(s)
    slugs = sorted(set(slugs))
    todo = [s for s in slugs if data.get(s, {}).get("status") in (None, "error")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(slugs)} slugs total, {len(todo)} to fetch", flush=True)

    def work(slug):
        try:
            status, body = fetch(f"greek-dictionary/{slug}")
        except Exception as e:  # noqa: BLE001 — record and move on; rerun to retry
            print(f"  ERROR {slug}: {e}", flush=True)
            return slug, {"status": "error", "error": str(e)}
        if status != 200:
            return slug, {"status": status}
        rec = parse_node(body)
        rec["status"] = 200
        return slug, rec

    done = 0
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for slug, rec in ex.map(work, todo):
            data[slug] = rec
            done += 1
            if done % 50 == 0 or done == len(todo):
                OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True),
                               encoding="utf-8")
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(todo)}  ({rate:.1f}/s, ~{(len(todo)-done)/max(rate,0.01)/60:.0f} min left)",
                      flush=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")

    ok = sum(1 for r in data.values() if r.get("status") == 200)
    lex = sum(1 for r in data.values() if r.get("type") == "lexicon")
    print(f"saved {len(data)} entries ({ok} fetched, {lex} lexicon nodes) to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
