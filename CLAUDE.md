# Greek New Testament Dictionary

**The pages moved (28 Sept 2026).** The Dictionary is part of BillMounce.com, so its pages now live in [teknia53/billmounce-website](https://github.com/teknia53/billmounce-website), in `site/greek-dictionary/`, with the site header: the app page, the 24 letter pages and their index, and the sitemap. Make changes to them there. The letter pages are built there by `scripts/build-dictionary-pages.py`, which was `tools/build_pages.py` here.

What stays here:

- `proxy/`: the Worker `dictionary-proxy`, which serves www.billmounce.com/greek-dictionary/ and prerenders each word's entry for search engines. It stays after launch, when it reads the website's pages instead of this repo's copy (see `LAUNCH.md` in the website repo).
- `dictionary.dat` (the data) and the Drupal import tools in `tools/`.
- `site/` and the Pages project `greek-dictionary`: the old copy, which billmounce.com shows until the new site launches. If you change it to fix billmounce.com before launch, make the same change in the website's pages.

The entries come from the API Worker `flashworksbible-api` (repo teknia53/bible), which the Interlinear Bible uses too.

## Bill's related projects

Bill works on these both on his Mac and in claude.ai cloud sessions. The copy on his Mac may lag GitHub, and a cloud session can't see his Mac, so this list is the shared map. Keep it in step with `~/.claude/CLAUDE.md` on his Mac, and update the row when a project's hosting or status changes. All repos are under GitHub `teknia53`; Cloudflare (Workers, D1, Pages) is bill@teknia.com.

| Repo | What it is |
|---|---|
| billmounce-website | **The new billmounce.com**, replacing Drupal; launch pending in Oct 2026. Netlify (new.billmounce.com until launch), Supabase project **BillMounce** (`jqpfjxsetosljofxdvuv`), Stripe, Postmark, Mailjet. It also holds the site's copies of the Dictionary, Interlinear Bible, FlashWorks and ParseWorks pages. See its `LAUNCH.md`. |
| gwotd-email | Greek Word of the Day **daily email drip** (gwotd.billmounce.com): Worker + D1 `gwotd` + Resend. Reads the words from the website's Supabase. |
| gwotd | Greek Word of the Day **mobile app** (React Native). |
| dictionary | Greek Dictionary. Its pages moved to the website repo; the `dictionary-proxy` Worker stays here. |
| bible | Interlinear Bible: D1 `flashworksbible` + `flashworksbible-api` Worker (also used by the Dictionary). Its page moved to the website repo. |
| flashworks / flashworksapp / parseworks | FlashWorks web and iOS apps; ParseWorks (its proxy Worker serves `/pw/api`). |

- **Two Supabase projects:** "BillMounce" is the live website. "Greek Videos" (`bfjpaedtimbjjqavldhk`) belongs to the older video.billmounce.com app.
- **Videos:** the site embeds ~475 Vimeo videos. Bill decided (2 Oct 2026) to move them all to Bunny.net.
- **Secrets:** never put API keys or tokens in chat or git.
