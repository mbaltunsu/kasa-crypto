"use client";

import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { formatAmount } from "@kasa/shared";
import { useAssetMap, useDeposits } from "@/api/queries";

/** Watches the polled deposits query and toasts once when a deposit transitions into `credited`.
 * Mounted in the authenticated layout so the notification fires from any page. */
export function DepositNotifier() {
  const deposits = useDeposits();
  const { map: assets } = useAssetMap();
  const lastStatus = useRef<Map<string, string>>(new Map());
  const primed = useRef(false);

  useEffect(() => {
    const items = deposits.data?.items;
    if (!items) return;
    const seen = lastStatus.current;
    for (const d of items) {
      const before = seen.get(d.id);
      // Only on a real transition into credited — not the first load of already-credited rows.
      if (primed.current && before && before !== "credited" && d.status === "credited") {
        const asset = assets.get(d.asset_id);
        const amount = asset ? `${formatAmount(asset, d.amount)} ${asset.symbol}` : d.symbol;
        toast.success(`Deposit credited: ${amount}`);
      }
      seen.set(d.id, d.status);
    }
    primed.current = true;
  }, [deposits.data, assets]);

  return null;
}
