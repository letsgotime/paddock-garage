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

```
public/            deployed as-is by the Workers assets binding
  index.html       the vehicle profile, fully self-contained, ~1MB
  og/garage.png    OG card, regenerate with tools/og-image.py
  robots.txt       real file; Cloudflare's synthesized one is off
  sitemap.xml
tools/og-image.py  OG card generator, needs Pillow
wrangler.toml      name must stay "paddock-garage" or Workers Builds fails
```

`public/index.html` inlines all styles, scripts, and imagery. There is no build step and
no runtime external requests. Edit it with targeted string replacement, not wholesale
rewrites, and grep rather than reading the whole file.

## Deploy

`npx wrangler deploy` from this directory. Auth is a local wrangler OAuth token; it does
not exist in cloud environments, which is why cloud routines prepare changes but never
publish them.

Workers Builds (deploy on push to `main`) is the intended path. Once connected, pushing
becomes the deploy and local `wrangler deploy` should stop, so the two never race.

Note: the live HTML returns 403 to server-side fetches. That is Super Bot Fight Mode
challenging non-browser traffic, and it is correct behavior. Read `public/index.html` from
the repo instead; the repo is the source of truth, not the rendered page.
