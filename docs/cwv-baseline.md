# Core Web Vitals Baseline (T0.6)

**Status: INCOMPLETE — Phase 6 stays gated.**

## Why this is incomplete

The PageSpeed Insights API rejects keyless requests from this environment:

```
{ "error": { "code": 429,
  "message": "Quota exceeded for quota metric 'Queries' and limit 'Queries per day'
               of service 'pagespeedonline.googleapis.com'" } }
```

LCP, INP, CLS and TBT cannot be measured without one of:

1. A **PSI API key** (`NEEDS-OWNER-INPUT`) — then re-run the commands at the bottom of this file; or
2. **Search Console / CrUX field data** — blocked on T7.3 property verification; or
3. A local Lighthouse run (`npx lighthouse`) — needs a working local build of the frontend,
   which is itself blocked (see `docs/BLOCKED.md`).

**Do not start Phase 6 against the table below.** Transfer weight and TTFB are not Core Web
Vitals and will not tell you whether the perf work moved LCP or CLS. The audit is right that
without a before-picture there is no way to prove the perf work did anything.

---

## What *was* measurable (5 Sep 2026)

Measured with `curl` from a single client (Windows, residential connection). Server HTML
only — no subresources, no JS execution, no rendering. Median of one request each; treat as
indicative, not a benchmark.

| URL | HTML transfer (KB) | TTFB (s) | Total transfer (s) |
|---|---|---|---|
| `/` | 61.0 | 0.923 | 1.318 |
| `/india-gold-prices` | 106.8 | 0.746 | 1.330 |
| `/dubai-gold-prices` | 78.4 | 0.800 | 1.196 |
| `/gold-rates/kerala.html` | 11.0 | 0.626 | 0.825 |
| `/trends` | 67.7 | 0.756 | 1.162 |

### Observations worth carrying into Phase 6

- **TTFB is 0.63–0.92 s on every route.** That is a substantial fixed cost before any
  rendering starts, and it will sit directly in front of LCP. The rate pages are
  server-rendered against a live API whose `/api/rates` handler caches for 300 s
  (`ai_cache.set("rates", response, ttl_seconds=300)`), so a portion of these requests are
  paying for an uncached upstream fetch. Worth checking whether the Next.js layer adds its
  own caching or refetches per request.
- **`/india-gold-prices` ships 107 KB of HTML** — the heaviest route, and 1.75x the
  homepage. A large share is the React flight payload; note that the FAQ answer text is in
  that payload but *not* in the DOM (T0.7), so the page is paying to transfer text it never
  renders.
- **`/gold-rates/kerala.html` is 11 KB and has the fastest TTFB** — it is a flat static file.
  It is also the page publishing prices 10% wrong. Fast and wrong.
- Every app-rendered page carries the 4x-duplicated ticker (28 anchors), which is both a CLS
  risk above the fold (T6.1) and pure transfer waste.

---

## Fill this in once a PSI key exists

Set `PSI_KEY` and run:

```bash
for u in "/" "/india-gold-prices" "/dubai-gold-prices" "/gold-rates/kerala.html" "/trends"; do
  for s in mobile desktop; do
    curl -s "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https%3A%2F%2Fgoldpricewatch.com${u//\//%2F}&strategy=$s&category=performance&key=$PSI_KEY" \
      -o "psi_$(echo "$u" | tr -d '/').$s.json"
  done
done
```

Then record, for **mobile and desktop separately**:

| URL | Strategy | LCP | INP | CLS | TBT | Page weight | LCP element |
|---|---|---|---|---|---|---|---|
| `/` | mobile | | | | | | |
| `/` | desktop | | | | | | |
| `/india-gold-prices` | mobile | | | | | | |
| `/india-gold-prices` | desktop | | | | | | |
| `/dubai-gold-prices` | mobile | | | | | | |
| `/dubai-gold-prices` | desktop | | | | | | |
| `/gold-rates/kerala.html` | mobile | | | | | | |
| `/gold-rates/kerala.html` | desktop | | | | | | |
| `/trends` | mobile | | | | | | |
| `/trends` | desktop | | | | | | |

Targets for the after-table (T6.3): mobile LCP < 2.5 s, CLS < 0.1, INP < 200 ms.

**Note:** if the `/gold-rates/*.html` pages are rebuilt onto the app layout (T2.3), the
kerala row here stops being comparable — capture its after-numbers under the new route and
say so in the after-table rather than comparing a static file to a rendered route.
