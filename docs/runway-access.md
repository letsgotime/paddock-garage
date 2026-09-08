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

Zero Trust is a separate dashboard from the one that holds Workers and DNS. It is not reachable
from the Workers pages. Go straight to it:

    https://one.dash.cloudflare.com/<your account id>

The account id is the long hex string in any dash.cloudflare.com URL.

**Do not use the Access tab on the paddock-garage Worker's own page.** That gates the public
site. The Worker being gated here is a different one that does not exist yet.

## 1. Turn on one-time PIN login (3 minutes)

New Zero Trust organisations use the Cloudflare account itself as the default login method, so
the PIN method has to be added once. If it is already listed, skip this step.

1. **Zero Trust**, then **Integrations**, then **Identity providers**.
2. Under **Your identity providers** select **Add new identity provider**.
3. Select **One-time PIN**. Save.

The PIN emails come from `noreply@notify.cloudflare.com`. If you filter mail, let that sender
through.

Cloudflare's own account is also offered as a login method. It needs no setup and is fine for
you alone, but a reader without a Cloudflare account cannot use it, which is the whole point of
the email list. One-time PIN is what makes a plain address work.

## 2. Put the reader list straight in the policy (4 minutes)

Older versions of this document sent you to **Access controls**, **Rule groups** to build a
named group first. Rule groups have moved out of that menu, and a group buys nothing at this
size: a group is only a reusable list, and the policy can hold the addresses itself. Adding a
reader later is then one edit to the policy instead of one edit to a group.

1. **Zero Trust**, then **Access controls**, then **Policies**.
2. **Add a policy**. Name it `Runway readers`. Action: **Allow**.
3. Under **Include**, choose the selector **Emails** and enter your own address, the one you
   will log in with. Add any other readers on their own lines.
4. Policy session duration: **24 hours**. Save.

A saved policy on its own protects nothing. It does not take effect until an application in
step 3 is attached to it, and the dashboard will not warn you about that.

## 3. Create the application (8 minutes)

1. **Zero Trust**, then **Access controls**, then **Applications**, then **Create new
   application**.
2. Choose **Self-hosted and private**, leave the destination type on **Public DNS**, then
   **Continue with Self-hosted and private**.
3. Under **Destinations**, **Public hostnames**: subdomain `runway`, domain `paddock20.com`
   from the dropdown, path empty. The whole host is private. This field is the one that binds
   the gate to the hostname, and leaving it blank is the mistake that silently leaves the host
   open.
4. Scroll to **Access policies**, open **Add existing policy**, and select
   `Runway readers (allow)`. It should then be listed at Order 1 with the action Allow. There
   is also an `Owner (allow)` policy in that list; it is not needed here.
5. **Authentication**: one-time PIN is likely your only provider, in which case **Accept all
   available identity providers** is equivalent to selecting it and can be left on. If you ever
   add a second provider, come back and name one-time PIN explicitly so the other cannot become
   a second door.
6. **Details**: the name auto-fills from the subdomain; `Runway` reads better. Session duration
   24 hours (the policy's own duration supersedes it anyway).
7. The **Preview** panel should read: sources *All authenticated users*, policies
   *Runway readers*, destinations *runway.paddock20.com*. Then **Create**.

The hostname does not have to exist yet. The Worker deploy in step 5 creates the DNS record,
and by then the application is already in front of it.

## 4. Confirm the application actually exists (1 minute)

Do not skip this. A policy can save while the application silently does not, which leaves you
believing the gate is up when nothing is enforcing anything.

Go back to **Access controls**, **Applications**. There must be a row reading `Runway`, with
destination `runway.paddock20.com` and policy `Runway readers`. If the page still shows the
"add your first application" panel, the application was never created: repeat step 3.

## 5. Tell the week script the gate exists (1 minute)

Open the owner defaults file:

    open -e ~/.garage/runway.json

Change `"access_configured": false` to `"access_configured": true`. While you are there, put
your real figures in the other four fields (they are placeholders until you do); they never
leave this machine. Save.

## 6. Deploy the Worker (2 minutes)

From the repository folder:

    python3 tools/gig.py export --full && python3 tools/runway.py
    npx wrangler deploy -c wrangler.runway.jsonc

`private-src/runway/` is the Worker's asset root, so every file in it is served on the
hostname. The full export deliberately lands in `private-src/runway-data/` instead, and
`tools/runway.py` refuses to finish if anything but `index.html` is left in the asset root.

From now on `tools/week --deploy` deploys both Workers, garage first, runway second, and skips
runway again if `access_configured` is ever set back to false.

## 7. Prove the gate is real (4 minutes)

Curl is useless here: Cloudflare's bot protection answers it with a 403 and a "Just a moment"
challenge whether or not Access exists, which looks exactly like a working gate. Use these two
checks instead.

1. Open `https://runway.paddock20.com/cdn-cgi/access/get-identity` in a browser.
   * `{"err":"no app token set"}` means Access is in front of the host and sees no session.
     This is what you want before logging in.
   * A bare `404 Not Found` means **no Access application covers this hostname**. The page is
     open to the internet. Take the Worker down immediately with
     `npx wrangler delete -c wrangler.runway.jsonc`, then fix step 3.
2. In a private window open `https://runway.paddock20.com`. You should get the Cloudflare
   Access login page, titled "Log in to Runway", before any content. Enter your email, then the
   PIN from the mail. The page appears.

Then enter an address that is not on the list. It should be refused after the PIN step.

## Adding or removing a reader

**Zero Trust**, **Access controls**, **Policies**, `Runway readers`: add or remove the address,
save. A removed reader is refused at their next login; to cut a live session short, open the
application and use **Revoke existing tokens**.

## What Runway shows, and what stays in the warehouse

Every settled day with every dollar, per-hour figures on both clocks, and the replacement
arithmetic on your defaults. Never: per-order tips, store streets, clock times, the purpose of
each drive, the account column, or captured mail. The page is read-only; the warehouse is the
only place anything is entered.
