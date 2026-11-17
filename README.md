# Convertible Top Pricing

Personal-use app for convertible-top pricing and labor times from Robbins,
GAHH, and EZON. Search by year / make / model; every supplier's listings for
that vehicle are shown with MSRP, install labor hours, and total.

## Live app

GitHub Pages serves `index.html` from the `main` branch
(`https://jeremyshanebrook.github.io/convertible-top-pricing/` once Pages is
enabled in repo Settings → Pages → Deploy from branch `main`, `/ (root)`).
The app is a single self-contained page with the catalog bundled in — it
works offline once loaded. The labor rate is stored on the device
(`ctp-labor-rate-cents` in local storage).

## Rules the data follows

- **MSRP only** — discounts and sale prices are disregarded.
- **Robbins 2026 price book wins** over the Robbins website for Robbins
  prices and for labor times across all suppliers. If the book has no time
  for a part, the higher of the GAHH/EZON times is used. Hours are never
  invented.
- **Longer time wins** when hours differ for the same part across fits or
  divisions. Combo ≈ top-only + window-only − 1h (sometimes 2h).
- **Multi-fit tops** get a listing for each car they fit, at the higher
  book price.
- **Robbins materials come only from the book's price columns** for that
  part — no invented options (e.g. no "just vinyl").
- **Style lines:** tops with construction variations show a style line just
  above the window-type line ("Original style" for factory/original;
  descriptive otherwise, e.g. "Non-original one-piece top, no deck seams").
  Original style sorts first. Miata and S2000 rows also show a rain-rail
  line; EZON drip rails are a separate line. Where the data does not decide
  originality, the label is descriptive only and no reorder happens.
- **Completeness:** every book/catalog entry is in, or explicitly excluded
  with a reason. Other parts (cables, headliners, well liners, window
  sections, etc.) are included wherever the supplier sells them.

## Layout

- `index.html` — the built app (single file, catalog inlined). This is what
  GitHub Pages serves.
- `data/robbins.json`, `data/gahh.json`, `data/ezon.json` — the source
  catalog, 19,450 rows (Robbins 10,648 / GAHH 1,886 / EZON 6,916).
- `scripts/` — the build and reconcile scripts that produced the catalog
  from the supplier sites and the Robbins 2026 price book, plus the
  style-label pass (`apply_style_labels.py`).

## Branches

- `main` — the live site. Nothing merges here until Jeremy says a version
  is final.
- `develop` — testing / work in progress. Changes land here first.

## Updating

1. Edit the data or scripts, rebuild `index.html` from the catalog.
2. Commit to `develop`, verify, then merge to `main` on Jeremy's go-ahead.
3. Pushing to `main` updates the live site. Prices refresh monthly (1st):
   sample a few listings per supplier, calculate the % change, cross-check
   other samples, apply that % across the supplier only if the samples
   agree — otherwise flag it in the refresh log and change nothing.
