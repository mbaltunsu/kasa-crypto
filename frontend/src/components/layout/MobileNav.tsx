"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Menu, X } from "lucide-react";
import { SidebarContent } from "@/components/layout/SidebarContent";

/** Mobile-only hamburger + slide-in drawer. The trigger lives in the TopBar (below `md`); the
 * drawer reuses the exact desktop shell so the two never drift. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
        aria-expanded={open}
        className="-ml-1 grid h-9 w-9 place-items-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-ink md:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      {open
        ? createPortal(
            // Portal to <body> so the fixed overlay escapes the TopBar's `backdrop-blur`
            // containing block (a backdrop-filter ancestor would otherwise trap `position: fixed`).
            <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
              <button
                type="button"
                aria-label="Close menu"
                onClick={close}
                className="absolute inset-0 animate-fade-up bg-bg/70 backdrop-blur-sm"
              />
              <div className="absolute inset-y-0 left-0 flex w-64 max-w-[82%] flex-col border-r border-border/60 bg-surface shadow-pop">
                <SidebarContent onNavigate={close} />
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close menu"
                className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-lg bg-surface/80 text-muted ring-1 ring-border/70 transition-colors hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
