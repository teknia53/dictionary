# Greek New Testament Dictionary

**The pages moved (28 Sept 2026).** The Dictionary is part of BillMounce.com, so its pages now live in [teknia53/billmounce-website](https://github.com/teknia53/billmounce-website), in `site/greek-dictionary/`, with the site header: the app page, the 24 letter pages and their index, and the sitemap. Make changes to them there. The letter pages are built there by `scripts/build-dictionary-pages.py`, which was `tools/build_pages.py` here.

What stays here:

- `proxy/`: the Worker `dictionary-proxy`, which serves www.billmounce.com/greek-dictionary/ and prerenders each word's entry for search engines. It stays after launch, when it reads the website's pages instead of this repo's copy (see `LAUNCH.md` in the website repo).
- `dictionary.dat` (the data) and the Drupal import tools in `tools/`.
- `site/` and the Pages project `greek-dictionary`: the old copy, which billmounce.com shows until the new site launches. If you change it to fix billmounce.com before launch, make the same change in the website's pages.

The entries come from the API Worker `flashworksbible-api` (repo teknia53/bible), which the Interlinear Bible uses too.
