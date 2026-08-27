# Paddock Garage

A tracker and tool for real vehicle and gig-work economics, with a blog overlay as
its public face. Served as a static-assets Cloudflare Worker at
**https://garage.paddock20.com**.

The engine is measured cost per mile, built from real charging invoices and real
telemetry rather than estimates. The published pages are the surface; the tool is
the point.

**Read [CLAUDE.md](CLAUDE.md) before changing anything.** It covers what belongs on
the public surface versus what stays private, the data sources, and the hard rules
on privacy and on labeling measured figures against modeled ones.

## Layout

```
public/index.html   the vehicle profile (self-contained, no external assets)
public/og/          OG card
public/robots.txt   real file, plus sitemap.xml
tools/og-image.py   OG card generator
wrangler.toml       Worker name, assets binding, custom domain route
```

`public/index.html` is fully self-contained: styles, scripts, and images are all
inlined, so the site has no build step and makes no external requests at runtime.

## Deploy

```bash
npm install
npx wrangler deploy
```

Auth is a local wrangler OAuth token, so deploys happen from a machine that has it.
Cloud automation prepares changes and opens pull requests; it does not publish.

## Local preview

```bash
npx wrangler dev
```
