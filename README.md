# Paddock Garage

Vehicle dashboard for the Paddock fleet, served as a static-assets Cloudflare
Worker at **https://garage.paddock20.com**.

Built to hold more than one car — the current page covers PADDOCK MOBILE.

## Layout

```
public/index.html   the dashboard (self-contained, no external assets)
wrangler.toml       Worker name, assets binding, custom domain route
```

`public/index.html` is fully self-contained: styles, scripts, and images are
all inlined, so the site has no build step and no external requests.

## Deploy

```bash
npm install
npx wrangler deploy
```

The first deploy asks for Cloudflare auth in a browser, then binds
`garage.paddock20.com` and creates the DNS record automatically. Every deploy
after that is a single command.

## Local preview

```bash
npx wrangler dev
```
