"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FolderOpen, ClipboardList, ShoppingCart, Calculator, CheckSquare,
} from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/drawings", label: "Drawing Library", icon: FolderOpen },
  { href: "/review", label: "Review Center", icon: CheckSquare },
  { href: "/procurement", label: "Procurement", icon: ShoppingCart },
  { href: "/calculations", label: "Calculations", icon: Calculator },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r border-border bg-white flex flex-col">
      <div className="h-16 flex items-center px-5 border-b border-border">
        <div className="w-7 h-7 rounded-industrial bg-accent flex items-center justify-center text-white font-bold text-sm">
          E
        </div>
        <div className="ml-2 leading-tight">
          <div className="text-sm font-semibold">Drawing Intelligence</div>
          <div className="text-[11px] text-steel">&amp; BOM System</div>
        </div>
      </div>
      <nav className="flex-1 py-3">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-5 py-2.5 text-sm font-medium border-l-2 transition-colors ${
                active
                  ? "border-accent text-accent bg-accent-light/40"
                  : "border-transparent text-steel hover:text-graphite hover:bg-surface"
              }`}
            >
              <Icon size={17} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-4 border-t border-border text-[11px] text-steel-light">
        Engineering Drawing Intelligence &amp; BOM System v0.1
      </div>
    </aside>
  );
}
