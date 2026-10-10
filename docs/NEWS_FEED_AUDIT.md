# News feed audit and implementation notes

Date: 2026-10-10 (Asia/Kolkata)

## What changed

- Added one bulk feed endpoint at `/api/news/feed`. It runs broad US and India market searches plus searches for the selected set of tracked symbols, merges those with configured company-news results, validates symbols, removes duplicates, rejects items outside the selected 1/7/30-day window, and sorts by publication time.
- The endpoint performs fresh RSS searches on each request. The browser bypasses its cache when opening News and when the user refreshes or changes market / time filters. “For you” and “My stocks” fetch the broad set after a region-only search, so they cannot accidentally stay narrowed to India or US results.
- Search results are limited to configured publisher domains. Direct company-provider results additionally require an approved publisher name, which excludes social posts and low-confidence syndicated commentary from the curated news view.
- Cards show the publisher, headline, publication time, linked source, and ticker when available. Summary text and images appear only when a provider supplies them. An unavailable image falls back to a publisher initial; the feed does not invent photos. Provider records marked stale are labeled “Saved copy · may be old.”
- Removed the tall sticky feed header that covered the first article while scrolling. The app navigation remains fixed; feed controls stay in normal document flow. Opening News resets the main scroll container to the top.

## Sources and attribution

The live headline search uses Google News RSS as a discovery transport and accepts result publisher URLs only from the app's configured allowlist. The current list covers Reuters, Bloomberg, WSJ, CNBC, Financial Times, AP, BBC, Yahoo Finance, MarketWatch, Moneycontrol, Economic Times, Business Standard, Livemint, The Hindu BusinessLine, NDTV, Indian Express, Investor's Business Daily, The Motley Fool, Investopedia, and SEC.gov for permitted crawling. Direct company headlines are independently checked against the named publisher allowlist.

RSS descriptions are excerpts, not full articles. Headlines link to the source result (Google News redirects RSS article links to the publisher); company-provider entries link to their provider article URL. Full article access, images, rate limits, freshness, robots rules, and regional coverage are controlled by each publisher and provider. Wikipedia is not treated as a news publisher; it may be useful for background research but is not a breaking-news feed. Crawling public pages remains restricted by the existing allowlist, public-host validation, robots rules, and request limits.

## Live sample and quality checks

On 2026-10-10, a live seven-day combined request returned 14 stories from 8 named publishers. The corresponding market filters returned 11 US stories and 3 India stories at that moment. This is a sample, not a guaranteed count; source coverage changes between refreshes. Publisher imagery was sparse in the sample, so most cards correctly used the source-initial fallback. One provider record was identified as saved/stale and presented with a stale-data label.

The browser also exercised the India filter, 30-day range, publisher search, and reload path at a 390-pixel mobile viewport. Switching between regional and broad filters now issues a new scoped request. The fixed overlap shown in the supplied screenshot is removed by keeping the complete feed controls outside sticky positioning.

## Remaining limits

- Search results depend on RSS/search provider availability. This is a multi-publisher discovery feed, not a direct paid feed subscription or a complete market-news archive.
- A live India run returned only three recent stories in the sample window. A broader 30-day range can find additional older coverage, but cannot guarantee a minimum number of current India headlines.
- Some publishers do not provide a usable image or excerpt. Their cards remain text-first and attributed rather than borrowing unrelated imagery.
- Article URLs discovered through Google News RSS use its redirect URL so the publisher's original URL is opened by the redirect. Publisher pages may require a subscription, block crawlers, or change links.
- A full-text crawl is not run for every headline. The app's on-demand public-page crawler respects publisher restrictions; paywalled articles are not bypassed.
- The 45-second API deadline bounds waiting but does not guarantee every external provider responds. Failures are visible as an empty/error state with retry rather than fabricated results.
- Automated tests and small live/browser checks are not a capacity/soak test. Provider rate limits and high-load behavior still need a separate production-scale run.
