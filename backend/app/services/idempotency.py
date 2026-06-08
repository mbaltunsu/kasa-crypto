from __future__ import annotations

from uuid import UUID

# `ledger_transactions.idempotency_key` is a single global unique namespace. A client-supplied
# Idempotency-Key header is therefore namespaced by operation domain + acting user before it is
# stored, so the same client string can never alias across operations (e.g. a faucet key reused on
# a withdrawal) or across users. Without this, `ledger.post` would find the foreign transaction and
# return it without posting the intended legs (see findings #1 / #15).


def scoped_idempotency_key(*, domain: str, user_id: UUID, client_key: str) -> str:
    return f"{domain}:{user_id}:{client_key}"
