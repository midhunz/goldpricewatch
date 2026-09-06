# Blocked work — and why

**Date:** 5 September 2026

## The blocker

**The Next.js source for almost every page in the audit is not in this repository.**

`frontend/src/app` contains 7 routes:

```
frontend/src/app/page.tsx                      ->  /
frontend/src/app/trends/page.tsx               ->  /trends
frontend/src/app/calculator/page.tsx           ->  /calculator
frontend/src/app/gold-news-today/page.tsx      ->  /gold-news-today
frontend/src/app/gold-news-today/[slug]/page.tsx
frontend/src/app/news/page.tsx                 ->  /news
frontend/src/app/layout.tsx
```

The live site serves **38 routes**. Everything else exists only as *compiled* output in
the gitignored `prod-extract/frontend/.next/`, which is a deployment artifact, not source:

- All 7 country pages (`/india-gold-prices`, `/uae-gold-prices`, `/oman-`, `/qatar-`, `/saudi-arabia-`, `/bahrain-`, `/kuwait-`)
- All 5 India city pages (`/mumbai-`, `/bangalore-`, `/chennai-`, `/hyderabad-`, `/pune-`)
- All 4 emirate pages (`/dubai-`, `/abu-dhabi-`, `/sharjah-`, `/ajman-`)
- `/about`, `/contact`, `/privacy`, `/terms`, `/gold-prediction`, `/geopolitical-gold-impact`, `/why-gold-price-is-increasing-2026`
- `/login`, `/signup`, `/account`, `/admin`, `/portfolio`
- `robots.ts` and `sitemap.ts`
- The shared `Navbar`, `Footer`, ticker/marquee, and FAQ accordion components in their
  current form

### Evidence

- `git log --all --name-only` shows these files have **never** been committed on any branch.
  This is not a stale checkout; the source was never here.
- `.next/**/*.js.map` source maps are all `{"version":3,"sources":[],"sections":[]}` — empty,
  so the original TSX cannot be recovered from the build either.
- `prod-extract/` is gitignored (`.gitignore:41`).
- `frontend/public/` in git held only the five default Next.js SVGs. The real static assets
  (`og-image.png`, `/images/*`, `google28bb29abf1f4f276.html`, and the 15
  `gold-rates/*.html` files) existed only under `prod-extract/`.

### Consequence

Any task requiring an edit to those pages **cannot be implemented here**. Editing compiled
`.next` output would be overwritten by the next `npm run build`, and would not survive a
deploy. So it was not done.

### What was done about the assets

The real static assets were copied from `prod-extract/frontend/public/` into
`frontend/public/`, so they are now under version control and a fresh build will not 404
them. This was necessary to make the T1.1 fix deployable. It is also, on its own, a fix: 14
of the 15 rate pages referenced a hero image that returned 404 in production.

## How to unblock

One of:

1. **Locate the real frontend repo or branch** and work there. `main.py` shows this project
   is already split across repos — the gold rate scraper "runs on Prefect Cloud from
   github.com/midhunz/gold-price-scraper". The frontend source is likely similarly split.
2. **Pull the source off the deployment host**, if a build context or a source-containing
   image layer still exists there.
3. **Rebuild the missing pages from the compiled output.** The `.next/server/app/*/page.js`
   files contain the rendered strings, metadata objects and component structure, so the pages
   could be reconstructed. This is real work — roughly 26 routes plus shared components — and
   should be a deliberate decision, not a side effect of an SEO pass.

Until then, treat `prod-extract/` as the only record of what production serves, and do not
delete it.

---

## Also worth your attention

### The production database password is in plaintext in `.env`

`.env` (gitignored, so not committed) contains a full Supabase Postgres connection string
for what appears to be the production database, including the password, under the key
`SUBA_BASE_URL`. Two things:

- That credential should be rotated and moved to a secret store, since it has been sitting
  in a plaintext file in a working directory.
- The line is also malformed: it uses `SUBA_BASE_URL:` (a colon, not `=`), so
  `os.environ.get("SUBA_BASE_URL")` in `supabase_scraper.py:34` will not read it. Anything
  depending on that variable is silently falling back to nothing.

It was not used to query production during this work.

### T5.3 is answerable from the code, not from the owner

The task list marks the data source as `NEEDS-OWNER-INPUT`. It is in the repo:
`backend/supabase_scraper.py:36` sets `BASE_URL = "https://gulfnews.com/gold-forex"`, and
the date parser is named `parse_gulfnews_date`. Rates are **scraped from Gulf News**.

Before writing "Source: Gulf News" onto every rate page as T5.3 asks, note that naming it
is also a public statement that the site republishes scraped figures from another
publisher's pages. Whether that is something to advertise — or to license properly first —
is a commercial and legal call, not an SEO one. Flagging it rather than shipping it.

### T1.4's cadence question is narrower than it looks

Nothing in this repo scrapes gold rates on a schedule. The APScheduler jobs in
`main.py` cover news (hourly), AI calculations (6-hourly) and model training (weekly) — no
rates. Per the comment at `main.py:280`, the rate scrape runs on Prefect Cloud in a separate
repo. So the true cadence behind the homepage's "Updated hourly" claim is defined **there**,
and the question to answer is specifically: *what is the schedule on the Prefect flow?*

`FEED_REFRESH_CADENCE_MINUTES` (env var, default 60) exists in `backend/rate_utils.py` so
the staleness guardrail can be corrected without a code change once that is known.

---

## Task-by-task status

Legend: **Done** · **Partial** — some of it landed, rest blocked · **Blocked** — needs the
missing frontend source · **Owner** — needs a real-world fact only the owner has

### Phase 0 — Recon

| Task | Status | Notes |
|---|---|---|
| T0.1 robots.txt | Done | `docs/phase0-recon.md` |
| T0.2 sitemap state | Done | 42 URLs; `lastmod` hardcoded; 15 state pages not 11 |
| T0.3 URL inventory | Done | `docs/url-inventory.md`; 6 true orphans found |
| T0.4 redirect matrix | Done | 2-hop `http://www` chain; Caddyfile fix committed |
| T0.5 structured data | Done | Only `FAQPage`, on the 3 wrong pages |
| T0.6 CWV baseline | **Partial / Owner** | PSI keyless quota exhausted; needs an API key. Weight + TTFB captured |
| T0.7 FAQ root cause | Done | Client accordion conditionally mounts the answer |

### Phase 1 — Data correctness

| Task | Status | Notes |
|---|---|---|
| T1.1 wrong `/gold-rates` prices | **Done** | All 15 files: `noindex`, every price removed, empty state, fabricated-timestamp JS deleted. Regression tests added |
| T1.2 permanent `0.00%` | **Partial** | Backend fixed: purity-key normalisation + `null` instead of `0.0`. Rendering the null as "nothing" needs the frontend |
| T1.3 no timestamp | **Partial** | API now returns feed-fetch `updated_at` and a `feed_stale` flag. Displaying it needs the frontend |
| T1.4 freshness claims | **Partial / Owner** | Removed from all 15 static pages. Homepage/`/about`/`/contact` blocked. True cadence lives in the Prefect repo |
| T1.5 Chennai = national rate | Blocked | Confirmed measured. Needs the city page source |
| T1.6 fake USD demo | Blocked | Needs homepage source |

### Phase 2 — Indexability

| Task | Status | Notes |
|---|---|---|
| T2.1 duplicate emirate pages | Blocked | Confirmed: identical 5 AED prices across all four |
| T2.2 state pages orphaned | **Partial** | Moot short-term (now `noindex`). Shared layout / index page / breadcrumbs blocked |
| T2.3 two templates | Blocked | Needs the app to absorb the static files |
| T2.4 trailing slash | Blocked | Needs `next.config` + link components |
| T2.5 no hreflang | Blocked | Confirmed 0 hreflang tags sitewide |
| T2.6 `/signup` indexable | Blocked | **Widen this task:** `/login`, `/account`, `/admin`, `/portfolio` are also `index, follow` |
| T2.7 hardcoded `lastmod` *(new)* | Blocked | Needs `sitemap.ts` |
| T2.8 news articles missing from sitemap *(new)* | Blocked | Needs `sitemap.ts` |

### Phase 3 — On-page

| Task | Status | Notes |
|---|---|---|
| T3.1 titles > 60 chars | **Partial** | Fixed on all 15 static pages (max now 44). 9 app pages blocked. CI lint added |
| T3.2 descriptions > 155 | **Partial** | Fixed on all 15 (max now 137). App pages blocked. CI lint added |
| T3.3 Open Graph defects | **Partial** | Static pages: absolute `og:image`, page-specific title/description, `og:site_name`/`og:type`/`og:locale`, full Twitter card. **New finding:** all 6 app rate pages have *no* `og:image` at all — blocked |
| T3.4 FAQ answers absent | Blocked | Root cause identified (T0.7). Fix needs the accordion component |
| T3.5 homepage H1 | Blocked | |
| T3.6 skipped heading level | **Done** | Static pages now H1→H2→H3; automated check in CI |
| T3.7 28 ticker anchors | Blocked | Confirmed 28 on every page |
| T3.8 Chennai anchor mismatch | Blocked | Confirmed exactly |
| T3.9 emoji in anchors | Blocked | Confirmed 5 on `/india-gold-prices` |
| T3.10 image audit | **Done (audit)** | 0 `<img>` elements — emoji throughout, so alt-text coverage is not applicable. `og-image.png` and `og-trends.png` return 200. **14 of 15 hero images 404'd** — fixed in the static files |

### Phase 4 — Content and keyword gaps

All blocked on the frontend source. T4.1 is done for the 15 static pages ("gold rate" in
every title, enforced by a test). T4.2 also needs a historical feed (**Owner**); T4.7 needs
retail spread data (**Owner**). T4.6 should stay parked — building 14 Kerala district pages
without district-varying data would add 14 thin duplicates.

### Phase 5 — E-E-A-T and structured data

| Task | Status | Notes |
|---|---|---|
| T5.1 structured data | **Recon done**, implementation blocked | It is "add", not "fix". Note the existing `FAQPage` markup is currently a guideline violation |
| T5.2 named author | **Owner** | Do not invent a person |
| T5.3 data source | **Answerable now** | It is `gulfnews.com/gold-forex` — see the caveat above before publishing it |
| T5.4 contact details | **Owner** | |
| T5.5 prediction methodology | Blocked / **Owner** | Needs the model's real inputs and backtest numbers |

### Phase 6 — Performance

| Task | Status | Notes |
|---|---|---|
| T6.1 ticker CLS | Blocked | |
| T6.2 `Loading latest rates...` thrash | **Done** | Eliminated with T1.1 |
| T6.3 perf pass | Gated | Correctly gated on T0.6, which needs a PSI key |

### Phase 7 — Monitoring

| Task | Status | Notes |
|---|---|---|
| T7.1 price sanity guardrails | **Done** | `backend/rate_utils.py`: zero/negative prices dropped, 22K/24K ratio band, state-vs-national 2% divergence, feed staleness. 33 unit tests |
| T7.2 SEO regression tests in CI | **Partial** | Implemented and wired into CI for the 15 static pages (24 tests). App-page equivalents need the source |
| T7.3 Search Console | **Owner** | Verification token is in place (`google28bb29abf1f4f276.html`, now in the repo) |

---

## Summary

| | Count |
|---|---|
| Done | 12 |
| Partial | 8 |
| Blocked on missing frontend source | 26 |
| Needs owner input | 7 |

The gating item — T1.1, the 10%-wrong prices on 15 indexed pages — is fully fixed and
covered by tests. Everything else that does not require the missing frontend source is
either done or has its blocker named above.
