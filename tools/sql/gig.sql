-- Shopper-app batches, reconciled against the car. Applied to Neon 2026-09-06; kept here so the
-- schema is in the repo. tools/gig.py owns the view (it bakes in the measured cost per mile).
create table if not exists garage.gig_batch (
  id                 bigserial primary key,
  occurred_on        date not null,
  accepted_at        timestamptz,
  platform           text not null default 'Instacart',
  account            text,                 -- whose shopper account. NULL until set on purpose.
  store              text,
  store_address      text,
  orders             int,
  items              int,
  units              int,
  batch_pay_usd      numeric,
  tips_usd           numeric,
  tips_initial_usd   numeric,              -- before customers changed them; NULL when the screen showed no change
  total_usd          numeric,
  heavy_pay          boolean,
  boost_pay          boolean,
  app_active_seconds int,                  -- the app's clock for this batch: accept to last drop-off
  route_miles        numeric,              -- sum of the app's per-leg distances; NULL if any leg is unknown
  sec_per_item       int,
  source             text not null default 'app-screenshot',
  source_files       text[],
  note               text,
  created_at         timestamptz default now(),
  unique (occurred_on, accepted_at, store)
);
create table if not exists garage.gig_order (
  id                    bigserial primary key,
  batch_id              bigint not null references garage.gig_batch(id) on delete cascade,
  label                 text,              -- 'A', 'B', or NULL for a single-order batch
  items_ordered         int,
  items_found           int,
  found_or_replaced_pct numeric,
  on_time               boolean,
  delivered_at          timestamptz,
  tip_usd               numeric,
  tip_initial_usd       numeric,
  drop_miles            numeric,
  refunds               int,
  replacements          int
);
create table if not exists garage.gig_day (
  occurred_on         date primary key,
  platform            text not null default 'Instacart',
  app_active_seconds  int,                 -- the app's clock for the day
  true_active_seconds int,                 -- the operator's own read of time worked, recorded verbatim
  true_active_note    text
);
