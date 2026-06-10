import { SidebarContent } from "@/components/layout/SidebarContent";

export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-border/60 bg-surface/50 md:flex">
      <SidebarContent />
    </aside>
  );
}
