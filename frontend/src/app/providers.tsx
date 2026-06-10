"use client";

import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Toaster, toast } from "sonner";

/** Pull a human-readable message out of an API error (the backend's {code,message,...} body),
 * a thrown Error, or anything else — so every failed mutation surfaces a useful toast. */
function errorMessage(error: unknown): string {
  if (error && typeof error === "object") {
    const e = error as { message?: unknown; detail?: unknown };
    if (typeof e.message === "string" && e.message) return e.message;
    if (typeof e.detail === "string" && e.detail) return e.detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
        // Every mutation that rejects shows its API error as a toast (rate limits, amount caps,
        // validation, etc.). Per-action success toasts live alongside each mutation's onSuccess.
        mutationCache: new MutationCache({
          onError: (error) => toast.error(errorMessage(error)),
        }),
      }),
  );
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster richColors closeButton position="top-right" theme="dark" />
    </QueryClientProvider>
  );
}
