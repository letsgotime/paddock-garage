# Paddock Garage

## What this is

A **tracker and tool** for real vehicle and gig-work economics, with a **blog overlay**
as its public face. The tool is the product. The published pages are the surface it
happens to show the world.

The engine is one idea: **measured cost per mile**, derived from real invoices and real
telemetry, applied to real decisions. Everything else is presentation.

## What this is NOT

- **Not a marketing site.** Not an ad property, not a lead magnet, not a content farm.
- **Not SEO-driven.** Do not pick topics by search volume. Do not write a page because a
  keyword has demand. Topics come from what Gavin actually needs to decide or track.
- **Not a brochure.** If a change would make sense only to an advertiser, it is wrong here.

An earlier session drifted into keyword targeting and audience optimization. That was a
misread. Correcting it is why this file exists.

## The two surfaces

**Public overlay** (deployed, indexable)
: Finished artifacts worth showing. Today that is the 2024 Model Y vehicle profile:
  measured running costs, the gas fleet it replaced, battery and efficiency data.

**Private tool** (never deployed to the public site)
: Operational and decision material. Gig-income research, pipeline tracking, income vs
  vehicle-cost modeling, anything about Gavin's finances or prospects. This lives in
  private artifacts or untracked local files. It does **not** go in `public/`.

When in doubt about which surface something belongs to, it is private.

## Data sources

| Source | Status | Gives |
|---|---|---|
| TezLab MCP | live, works locally and in cloud routines | drives, charges, battery health, efficiency, idle loss |
| Tesla charging invoices | manual CSV export | real per-kWh cost, the only true cost source |
| Recurrent | connected | market value, range score, fleet-model range |
| Tesla Fleet API | planned | direct telemetry and commands, independent of TezLab |

### Tesla Fleet API

**Registered domain: `garage.paddock20.com`.** Chosen because this host's deploy is fully
controlled here, unlike the apex, which is v0-managed and can clobber files on sync.

The keypair exists:

- **Public key**, committed and deployed, live at
  `https://garage.paddock20.com/.well-known/appspecific/com.tesla.3p.public-key.pem`
  (EC, prime256v1 / P-256, verified serving 200)
- **Private key** at `~/.tesla/paddock-garage-private.pem`, mode 600, **outside the repo**.
  It is not backed up anywhere. Losing it means re-registering and re-pairing every car.

**That public key file must never be deleted, moved, or renamed.** Since Tesla mobile app
4.30.0 it sits in the vehicle pairing chain of trust and is re-fetched, not checked once.
Removing it breaks pairing for every paired vehicle, and recovery means physically
re-pairing each car. If this project ever leaves this host, that one file stays behind.

Still to do, and it needs Gavin: create the app at developer.tesla.com with **Allowed
Origins = `garage.paddock20.com`** (must match the registered domain), then register the
partner account via `POST /api/1/partner_accounts`. Redirect URIs allow `localhost`
alongside a production URI on the same app, so the tool itself can run anywhere; it does
not have to live on this domain.

If registration rejects the key, one thing worth trying before anything else: the file
currently serves as `application/x-x509-ca-cert` (Cloudflare infers it from the extension).
A `_headers` file can force `text/plain` if Tesla turns out to be fussy about it.

## Hard rules

1. **Never publish the VIN serial.** The descriptor `7SAYGAEE8RF` may show; the last six
   characters stay masked, in text *and* in images. Image redaction means destroying the
   pixels, not a CSS overlay or a blur.
2. **Never publish home or work addresses.** City names and mileage are fine.
   This now extends to telemetry: drive coordinates cluster onto a home and a regular
   destination, so `/drive/` publishes city-to-city corridors and distances only.
   Per-drive coordinates and departure times stay out, because a departure pattern is
   a statement about when the house is empty. TezLab returns a street address on the
   private charger; it is listed by city only.
2b. **The driver carve-out (approved 2026-09-03).** Personal *context* is public: the
   one line on the home page and `/driver/`. Personal *figures* are not: income, debt,
   per-track earnings and financing terms stay in the private tool.
3. **Zero em dashes** in published pages. House standard, enforced by the rail-redline
   pass, because the em dash is a recognizable AI tell. Use colons, commas, or the word
   "to". Grep for `—` and `&mdash;` before committing; the page is currently at zero and
   must stay there.

   En dashes are *not* covered by that rule. They are ordinary typography in numeric
   ranges (`2015–2026`, `11–12 mpg`), and the page has about 98 of them legitimately. Do
   not "fix" them. If Gavin ever extends the standard to en dashes, change this line
   first, then the page.
4. **Label measured vs modeled, always.** A figure backed by an invoice or telemetry is
   measured. Everything else is modeled and must say so. Never present an estimate as a
   measurement. This is the credibility of the whole project.
5. **Sanity-check before writing.** If a data source returns something implausible
   (odometer going backwards, capacity above spec), report the anomaly instead of
   publishing it.

## Layout

The public site is **generated**, not hand-edited. Every published figure comes from
one JSON snapshot, which is what stops numbers going stale on one page while another
page moves on.

```
data/telemetry.json   the measured snapshot: TezLab + Fleet API + invoices
data/log.json         the dated entries shown on /switch/
content/legacy/*.html prose fragments lifted out of the old 1 MB page
tools/build.py        renders public/ from data + content   <- run this
tools/check.py        pre-deploy gate: privacy, dead links, page weight
tools/extract-legacy.py  one-time image and fragment extraction, already run
public/               GENERATED. Do not hand-edit a page here.
  assets/glass.css    the elevation system (e0/e1/e2)
  assets/garage.css   base reset, layout, charts, mobile-first breakpoints
```

**Do not hand-edit `public/*/index.html`.** Change `data/telemetry.json` or the page
functions in `tools/build.py`, then run:

```
python3 tools/build.py && python3 tools/check.py
```

`check.py` fails the build on an em dash, an exposed VIN serial, a street address, a
private coordinate, a dead internal link, or any page over 200 KB. It is the gate; do
not skip it.

`garage.css` carries the base reset (`box-sizing`, body margin, the Arial stack).
The legacy pages kept that reset in their own inline `<style>` and glass.css was only
ever an overlay on top of it, so a generated page without garage.css renders in Times
with a horizontal scrollbar.

### Site structure, set 2026-09-03

Six doors plus a seventh reached from the hero and footer. The wordmark is Home.

| Page | Carries |
|---|---|
| `/switch/` | The gas-to-electric story in seven chapters, plus the dated log |
| `/drive/` | Corridor map, miles per day, FSD share, efficiency vs the region |
| `/charge/` | Sessions, blended vs Supercharger rate, spend per day, locations |
| `/ledger/` | Cost per mile vs the gas fleet, value, warranty, what the car earns |
| `/battery/` | Degradation, cycles, phantom drain, warranty floor |
| `/car/` | Verified VIN, spec sheet as tabs, Juniper, Toybox, wrap downloads |
| `/driver/` | The context, the fleet before, where the privacy line sits |

`/case-study/`, `/log/` and `/log/model-y/` are retired and 301 to their new homes via
`public/_redirects`, which Workers Assets applies before serving any asset.

## Charts

Brand hues are too light for chart marks on `#05070D`. The marks use hues stepped into
the dark-mode OKLCH band (L .48 to .67, C >= .10) and validated for colour-vision
separation: ignition `#E84301`, sky `#0791C8`, amber `#B97504`, with steel `#7F8794`
as a neutral reference that never carries identity. UI accents keep the brighter brand
values. SVG text scales with the viewBox, so chart label sizes are set per breakpoint
in `garage.css` to land near 10px on screen; changing a chart's viewBox width means
retuning those.

## Deploy

`npx wrangler deploy` from this directory. Auth is a local wrangler OAuth token; it does
not exist in cloud environments, which is why cloud routines prepare changes but never
publish them.

Workers Builds (deploy on push to `main`) is the intended path. Once connected, pushing
becomes the deploy and local `wrangler deploy` should stop, so the two never race.

Note: the live HTML returns 403 to server-side fetches. That is Super Bot Fight Mode
challenging non-browser traffic, and it is correct behavior. Read `public/index.html` from
the repo instead; the repo is the source of truth, not the rendered page.

## Visual system: floating glass

The public site runs the ACC glass spec ported to the garage palette:
`public/assets/glass.css` holds the entire system and restyles every page
through the cascade (loaded after each page's inline styles). Three
elevations: e0 recedes (callouts, chips), e1 rests (cards, tiles, tables,
topics), e2 commands with the ignition ring, ONE per view. ~4.5% film
grain over a full-bleed backdrop plate.

Backdrop plates are bespoke Higgsfield generations (soul_location model,
21:9, no text or logos prompted) in `public/img/`: hero-ev-road (home),
hero-highway (case study), hero-charge (model-y), tex-carbon (log,
callback). Each page picks its plate via `--page-bg`.

**Imagery rule: backgrounds show EVs or EV lifestyle only.** No gas
vehicles, no grilles, no exhaust cues; prompt EV design language (closed
front, full-width light bars, charge ports, chargers). A generated plate
that shows readable AI text anywhere (a license plate counts) gets the
pixels redacted before shipping, same standard as the VIN rule.

The site is deliberately dark-only: the light-mode media blocks were
removed from every page, and the model-y theme toggle is hidden. Do not
reintroduce a light theme without a real design pass.
