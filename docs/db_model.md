# Data model

**Owner: Codex** (backend). Postgres + SQLAlchemy 2.x + Alembic. Seeded by Claude; Codex owns ongoing changes.
All amounts are integer base units stored as `numeric(78,0)` (holds uint256). Balance = `SUM(ledger_entries.amount)`.

## Tables

```text
users (
  id              uuid pk,
  email           citext unique not null,
  password_hash   text not null,
  role            text not null check (role in ('user','admin')),
  hd_index        bigint unique not null,         -- assigned at signup; drives deposit address derivation
  created_at      timestamptz not null default now()
)

assets (                                            -- read-model projection of the registry (seeded, not hand-edited)
  id               uuid pk,
  chain_id         int not null,
  symbol           text not null,
  type             text not null check (type in ('native','erc20','erc721')),
  contract_address text,                            -- null for native
  decimals         int not null,                    -- 0 for erc721
  unique (chain_id, symbol),                         -- NOTE: registry indexes symbols case-insensitively
  unique (chain_id, lower(contract_address))
)

deposit_addresses (
  id              uuid pk,
  user_id         uuid not null references users(id),
  address         text not null unique,             -- EIP-55 checksummed; compared lowercase
  derivation_path text not null,
  unique (user_id)                                   -- one EVM address reused across chains
)

-- Double-entry ledger: every transaction's entries SUM to zero per asset.
ledger_accounts (
  id          uuid pk,
  owner_type  text not null check (owner_type in ('user','system')),
  user_id     uuid references users(id),            -- null for system accounts
  asset_id    uuid not null references assets(id),
  name        text not null,                         -- e.g. 'wallet','hot_wallet','deposits_in_transit','fees'
  unique (owner_type, user_id, asset_id, name)
)

ledger_transactions (
  id               uuid pk,
  type             text not null,                    -- LedgerEntryType context (deposit/withdrawal/transfer/fee/...)
  ref_type         text not null,
  ref_id           text not null,
  idempotency_key  text unique not null,
  created_at       timestamptz not null default now()
)

ledger_entries (
  id              uuid pk,
  transaction_id  uuid not null references ledger_transactions(id),
  account_id      uuid not null references ledger_accounts(id),
  asset_id        uuid not null references assets(id),
  amount          numeric(78,0) not null,           -- SIGNED; no >= 0 check here
  created_at      timestamptz not null default now()
)
-- INVARIANT (enforced in service + tested): per transaction, SUM(amount) = 0 for each asset_id.

onchain_deposits (
  id            uuid pk,
  chain_id      int not null,
  tx_hash       text not null,
  log_index     int,                                 -- null for native transfers
  block_number  bigint not null,
  block_hash    text not null,                       -- reorg detection
  to_address    text not null,
  asset_id      uuid not null references assets(id),
  amount        numeric(78,0) not null check (amount >= 0),
  status        text not null check (status in ('seen','confirmed','credited','orphaned')),
  user_id       uuid references users(id),
  created_at    timestamptz not null default now(),
  unique (chain_id, tx_hash, log_index)              -- no double-credit
)

withdrawal_requests (
  id          uuid pk,
  user_id     uuid not null references users(id),
  asset_id    uuid not null references assets(id),
  chain_id    int not null,
  to_address  text not null,
  amount      numeric(78,0) not null check (amount > 0),
  status      text not null check (status in
                ('requested','approved','signing','broadcast','confirmed','failed','rejected')),
  tx_hash     text,
  nonce       bigint,
  attempts    int not null default 0,
  error       text,
  created_at  timestamptz not null default now()
)

chain_cursors (
  chain_id             int primary key,
  last_scanned_block   bigint not null,
  last_finalized_block bigint not null,              -- block_number + N confirmations gate
  updated_at           timestamptz not null default now()
)

hot_wallet_nonces (
  chain_id    int primary key,
  address     text not null,
  next_nonce  bigint not null,
  updated_at  timestamptz not null default now()
)
```

## Notes / invariants

- **Double-entry:** balances are never stored; `available` = Σ credited entries, `pending` = Σ
  seen/confirmed-but-uncredited deposits. A withdrawal debits the user account + credits a system account
  in one transaction; reversal posts the inverse.
- **Idempotency:** `ledger_transactions.idempotency_key` dedupes both the watcher (`chain_id:tx_hash:log_index`)
  and client-supplied `Idempotency-Key` headers.
- **Reorg:** if a `seen`/`confirmed` deposit's `block_hash` diverges from canonical → `orphaned` + a
  `reversal` ledger transaction.
- **Symbol casing:** registry indexes symbols UPPERCASE; align the DB constraint (`unique (chain_id, upper(symbol))`)
  or normalize at seed so `DEMO`/`demo` can't both insert. *(Codex to finalize.)*
- **Seed:** `assets` rows are generated from the registry via an Alembic data migration + idempotent
  `seed_assets.py`; a content-hash parity check asserts registry == DB at boot. See
  [types_and_registry.md](types_and_registry.md).
