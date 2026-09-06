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

-- Raw shopper-platform email, captured weekly by a scheduled routine. Parsed lazily: the
-- structured fields are filled only once a real statement format has been seen.
create table if not exists garage.gig_mail (
  id                bigserial primary key,
  gmail_message_id  text unique not null,
  gmail_thread_id   text,
  received_at       timestamptz,
  sender            text,
  subject           text,
  body_text         text,
  kind              text,        -- statement | batch | tip | account | promo | other
  parsed            jsonb,
  parsed_ok         boolean,
  captured_at       timestamptz default now(),
  captured_by       text         -- routine | manual
);
create index if not exists gig_mail_received_idx on garage.gig_mail (received_at desc);

-- Why the car went somewhere is a recorded fact, never inferred in a view. Added 2026-09-06.
alter table garage.drive
  add column if not exists purpose        text,   -- shift | personal | charge | unknown
  add column if not exists purpose_source text,   -- corroborated-app | corroborated-soc | operator
  add column if not exists purpose_note   text;
alter table garage.gig_batch
  add column if not exists store_arrival_at timestamptz,   -- the app's arrival time at the store
  add column if not exists store_miles      numeric;       -- the app's "your location -> store" leg
