#!/usr/bin/env python3
"""The BillMounce.com site header, shared by the Greek Dictionary and the Interlinear Bible.

The header (logo, slogan, and the drop-down menus) is a copy of the one on
www.billmounce.com. Every link points back to the website. The menu itself is
kept in site_menu.json, which is scraped from the live site.

Usage:
    python3 tools/site_header.py            # re-inject the header into the app pages
    python3 tools/site_header.py --sync     # first refresh site_menu.json from www.billmounce.com

Targets (marker blocks are replaced in place):
    Dictionary  site/index.html
    Bible       ~/Claude/FlashWorksBible/site/index.html

tools/build_pages.py imports head_html() / body_html() for the static letter pages,
so run it too after a --sync, then deploy both Pages projects.
"""

import html
import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

SITE_HOST = "https://www.billmounce.com"
HERE = Path(__file__).resolve().parent
MENU_FILE = HERE / "site_menu.json"
LOGO_FILE = HERE / "site_logo.svg"

TARGETS = [
    HERE.parent / "site" / "index.html",
    Path.home() / "Claude" / "FlashWorksBible" / "site" / "index.html",
    Path.home() / "Claude" / "FlashWorks" / "site" / "index.html",
    Path.home() / "Claude" / "ParseWorks" / "site" / "index.html",
]

HEAD_START, HEAD_END = "<!-- site-header-head:start -->", "<!-- site-header-head:end -->"
BODY_START, BODY_END = "<!-- site-header:start -->", "<!-- site-header:end -->"


# ---------------------------------------------------------------- menu scraping

class _MenuParser(HTMLParser):
    """Pull the two-level primary menu out of a billmounce.com page."""

    def __init__(self):
        super().__init__()
        self.menu = []
        self._level = 0          # 1 or 2 while inside a primary-menu link
        self._text = []
        self._current = None     # the level-1 item being filled

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        a = dict(attrs)
        cls = a.get("class", "")
        if "primary-menu__link--level-1" in cls:
            self._level = 1
            self._current = {"title": "", "href": a.get("href", ""), "children": []}
            self.menu.append(self._current)
            self._text = []
        elif "primary-menu__link--level-2" in cls and self._current is not None:
            self._level = 2
            self._current["children"].append({"title": "", "href": a.get("href", "")})
            self._text = []

    def handle_data(self, data):
        if self._level:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._level:
            text = " ".join("".join(self._text).split())
            if self._level == 1:
                self._current["title"] = text
            else:
                self._current["children"][-1]["title"] = text
            self._level = 0


def absolutize(href):
    if href.startswith("/"):
        return SITE_HOST + href
    return href


def scrape_menu(page_html):
    p = _MenuParser()
    p.feed(page_html)
    for item in p.menu:
        item["href"] = absolutize(item["href"])
        for child in item["children"]:
            child["href"] = absolutize(child["href"])
    return p.menu


def sync_menu():
    page = subprocess.run(
        ["curl", "-sfL", "-A", "Mozilla/5.0", SITE_HOST + "/"],
        capture_output=True, text=True, check=True,
    ).stdout
    menu = scrape_menu(page)
    if len(menu) < 3:
        raise SystemExit("Could not find the primary menu on the live site; site_menu.json left unchanged.")
    MENU_FILE.write_text(json.dumps(menu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"site_menu.json: {len(menu)} top-level items, "
          f"{sum(len(i['children']) for i in menu)} sub-items")
    return menu


def load_menu():
    return json.loads(MENU_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- rendering

CSS = """
.site-header { --sh-blue: #0067ac; background: var(--sh-blue); color: #fff; font-family: "Open Sans", Helvetica, Arial, sans-serif; box-shadow: 0 0 50px 0 rgba(255,255,255,0.3); position: relative; z-index: 100; }
.site-header *, .site-header *::before, .site-header *::after { box-sizing: border-box; }
.site-header__content { display: flex; align-items: center; justify-content: space-between; padding: 10px 4%; position: relative; }
.site-header .visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(1px,1px,1px,1px); white-space: nowrap; }
.header-logo__link { display: block; color: #fff; text-decoration: none; line-height: 0; }
.header-logo__link svg { display: block; width: 215px; height: 32px; max-width: 100%; height: auto; }
.site-branding { padding: 20px 0; }
.site-slogan { font-size: 16px; line-height: 1.5; padding-top: 8px; }

.header-navigation-wrapper { display: contents; }
.primary-menu { position: relative; }
.primary-menu__list { list-style: none; margin: 0; padding: 0; }
.primary-menu__list--level-1 { display: flex; flex-wrap: wrap; }
.primary-menu__list-item--level-1 { display: flex; position: static; transition: opacity 0.2s; }
.primary-menu__link { color: #fff; text-decoration: none; font-weight: 400; }
.primary-menu__link--level-1 { display: block; font-size: 20px; line-height: 30px; padding: 8px 0 8px 16px; }
.primary-menu__button-toggle { align-self: stretch; width: 24px; margin-left: 2px; padding: 0; appearance: none; border: 0; background: transparent; cursor: pointer; color: #fff; display: flex; align-items: center; justify-content: center; }
.primary-menu__button-icon { display: block; width: 8px; height: 8px; border-left: 2px solid currentColor; border-bottom: 2px solid currentColor; transform: translateY(-2px) rotate(-45deg); transition: transform 0.2s; }
.primary-menu__list--level-2 { position: absolute; top: 100%; left: 0; min-width: 100%; display: flex; flex-direction: column; gap: 4px; padding: 16px 0 16px 16px; background: var(--sh-blue); visibility: hidden; opacity: 0; transition: visibility 0.2s, opacity 0.2s; z-index: 1; }
.primary-menu__list-item--level-1:is(:hover, :focus-within, .is-open) > .primary-menu__list--level-2 { visibility: visible; opacity: 1; }
.primary-menu__list--level-1:has(.primary-menu__list-item--level-1:hover) .primary-menu__list-item--level-1:not(:hover) { opacity: 0.5; }
.primary-menu__link--level-2 { display: inline-block; font-size: 20px; line-height: 30px; padding: 4px 0; }
.primary-menu__link--level-2:hover { text-decoration: underline; }

.mobile-nav-button { display: none; width: 48px; height: 48px; padding: 0; border: 0; background: transparent; cursor: pointer; position: relative; flex-shrink: 0; }
.mobile-nav-button__icon, .mobile-nav-button__icon::before, .mobile-nav-button__icon::after { display: block; width: 38px; height: 3px; background: #fff; position: absolute; left: 5px; transition: transform 0.2s, background 0.2s; }
.mobile-nav-button__icon { top: 22px; }
.mobile-nav-button__icon::before { content: ""; left: 0; top: -11px; }
.mobile-nav-button__icon::after { content: ""; left: 0; top: 11px; }
.site-header.is-menu-open .mobile-nav-button__icon { background: transparent; }
.site-header.is-menu-open .mobile-nav-button__icon::before { top: 0; transform: rotate(45deg); }
.site-header.is-menu-open .mobile-nav-button__icon::after { top: 0; transform: rotate(-45deg); }

@media (width <= 1000px) {
  .mobile-nav-button { display: block; }
  .header-navigation-wrapper { display: none; position: absolute; top: 100%; left: 0; right: 0; background: rgba(14, 22, 34, 0.95); z-index: 100; }
  .site-header.is-menu-open .header-navigation-wrapper { display: block; }
  .header-navigation-wrapper__scrollable { padding: 32px; max-height: calc(100vh - 150px); overflow-y: auto; -webkit-overflow-scrolling: touch; }
  .primary-menu__list--level-1 { display: block; }
  .primary-menu__list-item--level-1 { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; opacity: 1 !important; }
  .primary-menu__link--level-1 { flex: 1 1 auto; font-size: 24px; line-height: 36px; padding: 8px 0; }
  .primary-menu__button-toggle { width: 60px; height: 52px; margin: 0; }
  .primary-menu__list--level-2 { position: static; display: none; flex-basis: 100%; min-width: 0; padding: 0 0 0 16px; gap: 0; background: transparent; visibility: visible; opacity: 1; transition: none; }
  .primary-menu__list-item--level-1:is(:hover, :focus-within) > .primary-menu__list--level-2 { display: none; }
  .primary-menu__list-item--level-1.is-open > .primary-menu__list--level-2 { display: block; }
  .primary-menu__list-item--level-1.is-open > .primary-menu__button-toggle .primary-menu__button-icon { transform: translateY(2px) rotate(135deg); }
  .primary-menu__link--level-2 { display: block; font-size: 18px; line-height: 27px; padding: 8px 0; }
}
"""

JS = """
(function () {
  var header = document.getElementById('site-header');
  if (!header) return;
  var button = header.querySelector('.mobile-nav-button');
  button.addEventListener('click', function () {
    var open = header.classList.toggle('is-menu-open');
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
  });
  var toggles = header.querySelectorAll('.primary-menu__button-toggle');
  function closeAll(except) {
    toggles.forEach(function (t) {
      var li = t.parentNode;
      if (li !== except) { li.classList.remove('is-open'); t.setAttribute('aria-expanded', 'false'); }
    });
  }
  toggles.forEach(function (t) {
    t.addEventListener('click', function (e) {
      e.preventDefault();
      var li = t.parentNode;
      closeAll(li);
      var open = li.classList.toggle('is-open');
      t.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  });
  document.addEventListener('click', function (e) {
    if (!header.contains(e.target)) closeAll(null);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeAll(null); header.classList.remove('is-menu-open'); button.setAttribute('aria-expanded', 'false'); }
  });
})();
"""


def head_html():
    """Font link + CSS. Goes inside <head>."""
    return (
        f"{HEAD_START}\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">\n'
        f"<style>{CSS}</style>\n"
        f"{HEAD_END}"
    )


def _logo_svg():
    svg = LOGO_FILE.read_text(encoding="utf-8").strip()
    return svg.replace("<svg ", '<svg role="img" aria-label="Bill Mounce" ', 1)


def body_html(menu=None):
    """The <header> element. Goes at the top of <body>."""
    menu = menu or load_menu()
    items = []
    for n, item in enumerate(menu, 1):
        title = html.escape(item["title"])
        href = html.escape(item["href"])
        if item["children"]:
            sub = "\n".join(
                f'          <li class="primary-menu__list-item primary-menu__list-item--level-2">'
                f'<a href="{html.escape(c["href"])}" class="primary-menu__link primary-menu__link--level-2">{html.escape(c["title"])}</a></li>'
                for c in item["children"]
            )
            items.append(
                f'        <li class="primary-menu__list-item primary-menu__list-item--level-1 primary-menu__list-item--has-children">\n'
                f'          <a href="{href}" class="primary-menu__link primary-menu__link--level-1 primary-menu__link--has-children">{title}</a>\n'
                f'          <button class="primary-menu__button-toggle" type="button" aria-controls="primary-menu-item-{n}" aria-expanded="false">'
                f'<span class="primary-menu__button-icon"></span><span class="visually-hidden">{title} sub-navigation</span></button>\n'
                f'          <ul class="primary-menu__list primary-menu__list--level-2 site-header__dropdown" id="primary-menu-item-{n}">\n'
                f"{sub}\n"
                f"          </ul>\n"
                f"        </li>"
            )
        else:
            items.append(
                f'        <li class="primary-menu__list-item primary-menu__list-item--level-1">\n'
                f'          <a href="{href}" class="primary-menu__link primary-menu__link--level-1">{title}</a>\n'
                f"        </li>"
            )
    menu_html = "\n".join(items)
    return f"""{BODY_START}
<header class="site-header" id="site-header">
  <div class="site-header__content">
    <div class="site-branding">
      <a class="header-logo__link" href="{SITE_HOST}/" rel="home">{_logo_svg()}</a>
      <div class="site-slogan">For an Informed Love of God</div>
    </div>
    <button class="mobile-nav-button" type="button" aria-controls="header-navigation-wrapper" aria-expanded="false">
      <span class="visually-hidden">Menu</span>
      <span class="mobile-nav-button__icon"></span>
    </button>
    <div class="header-navigation-wrapper" id="header-navigation-wrapper">
      <div class="header-navigation-wrapper__scrollable">
        <nav class="primary-menu" aria-label="Main navigation">
          <ul class="primary-menu__list primary-menu__list--level-1">
{menu_html}
          </ul>
        </nav>
      </div>
    </div>
  </div>
</header>
<script>{JS}</script>
{BODY_END}"""


# ---------------------------------------------------------------- injection

def _replace_block(text, start, end, replacement, path):
    i = text.find(start)
    j = text.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f"{path}: missing {start} … {end} markers")
    return text[:i] + replacement + text[j + len(end):]


def inject(path, menu):
    text = path.read_text(encoding="utf-8")
    text = _replace_block(text, HEAD_START, HEAD_END, head_html(), path)
    text = _replace_block(text, BODY_START, BODY_END, body_html(menu), path)
    path.write_text(text, encoding="utf-8")
    print(f"updated {path}")


def main(argv):
    menu = sync_menu() if "--sync" in argv else load_menu()
    for target in TARGETS:
        if target.exists():
            inject(target, menu)
        else:
            print(f"skipped (not found): {target}")
    print("Now run  python3 tools/build_pages.py  and deploy both Pages projects.")


if __name__ == "__main__":
    main(sys.argv[1:])
