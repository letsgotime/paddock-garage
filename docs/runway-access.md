# Putting Runway behind Cloudflare Access

Twenty minutes, once. After this, runway.paddock20.com asks for an email, sends a one-time PIN
to it, and only the addresses on your list get in. Adding or removing a reader is one line in
that list. Nothing about the page itself changes.

The page is rendered by `python3 tools/runway.py` into `private-src/runway/` (gitignored) and
served by its own Worker, `paddock-runway`, from `wrangler.runway.jsonc`. It must not be
deployed before the steps below are done: without the Access application in front of it the
hostname would be open to anyone.

You need: the Cloudflare login that holds the paddock20.com zone. Zero Trust on the Free plan
covers up to 50 users; the first time in, Cloudflare asks you to pick a team name and may ask
for a payment method on file (it does not charge for the Free plan).

## 1. Turn on one-time PIN login (3 minutes)

New Zero Trust organisations use the Cloudflare account itself as the default login method,
so the PIN method has to be added once.

1. In the Cloudflare dashboard go to **Zero Trust**, then **Integrations**, then
   **Identity providers**.
2. Under **Your identity providers** select **Add new identity provider**.
3. Select **One-time PIN**. Save.

The PIN emails come from `noreply@notify.cloudflare.com`. If you filter mail, let that sender
through.

## 2. Make the named list of readers (3 minutes)

1. Go to **Zero Trust**, then **Access controls**, then **Rule groups** (older dashboards call
   these Access Groups).
2. **Add a group**. Name it `Runway readers`.
3. Under **Include**, choose the selector **Emails** and enter your own email address, the one
   you will log in with. One address per line. This is the list you edit later to add or
   remove a reader.
4. Save.

## 3. Create the application (7 minutes)

1. Go to **Zero Trust**, then **Access controls**, then **Applications**.
2. **Add an application**, then **Self-hosted**.
3. Application name: `Runway`.
4. Under the public hostname, choose the domain `paddock20.com` from the dropdown and enter
   `runway` as the subdomain, so the application covers `runway.paddock20.com`. Leave the
   path empty: the whole host is private.
5. Session duration: 24 hours is right for this. A reader logs in once a day.
6. **Access policies**: add a policy.
   * Policy name: `Runway readers`
   * Action: **Allow**
   * Rule: **Include**, selector **Rule group**, value `Runway readers`
   Save the policy and make sure it is attached to the application. An application with no
   policy denies everyone, which is the safe failure.
7. **Login methods** (the Authentication tab): either accept all available identity providers
   or select **One-time PIN** only. Selecting PIN only is cleaner: readers never see a
   Cloudflare-account login they do not have.
8. Save the application.

The hostname does not have to exist yet. The Worker deploy in step 5 creates the DNS record,
and by then the application is already in front of it.

## 4. Tell the week script the gate exists (1 minute)

Open the owner defaults file:

    open -e ~/.garage/runway.json

Change `"access_configured": false` to `"access_configured": true`. While you are there, put
your real figures in the other four fields (they are placeholders until you do); they never
leave this machine. Save.

## 5. Deploy the Worker (2 minutes)

From the repository folder:

    npx wrangler deploy -c wrangler.runway.jsonc

From now on `tools/week --deploy` deploys both Workers, garage first, runway second, and skips
runway again if `access_configured` is ever set back to false.

## 6. Prove it (4 minutes)

1. In a private browser window open https://runway.paddock20.com. You should see Cloudflare's
   login page before any content. Enter your email, then the PIN from the mail. The page
   appears.
2. Enter an address that is not in the list. It should be refused after the PIN step.
3. If content appears without a login page, stop: go back to step 3 and check the application
   hostname matches `runway.paddock20.com` exactly and that the Allow policy is attached.

## Adding or removing a reader

**Zero Trust**, **Access controls**, **Rule groups**, `Runway readers`: add or remove the
address, save. A removed reader is refused at their next login; to cut a live session short,
open the application and use **Revoke existing tokens**.

## What Runway shows, and what stays in the warehouse

Every settled day with every dollar, per-hour figures on both clocks, and the replacement
arithmetic on your defaults. Never: per-order tips, store streets, clock times, the purpose of
each drive, the account column, or captured mail. The page is read-only; the warehouse is the
only place anything is entered.
