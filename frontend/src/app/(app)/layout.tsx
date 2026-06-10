import type { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { AuthGate } from "@/components/layout/AuthGate";
import { DepositNotifier } from "@/components/DepositNotifier";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <DepositNotifier />
      <div className="flex min-h-dvh">
        <Sidebar />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </AuthGate>
  );
}
