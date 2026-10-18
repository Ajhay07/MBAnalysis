"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, FolderOpen, ShoppingCart, Calculator, CheckSquare } from "lucide-react";
import { BrandLogo, BellowsIllustration } from "@/components/Brand";

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
    <aside className="w-[220px] shrink-0 bg-navy text-white flex flex-col sticky top-0 h-screen">
      <div className="h-20 flex items-center px-5 border-b border-navy-line">
        <BrandLogo />
      </div>
      <nav className="pt-4 space-y-0.5">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-5 py-2.5 text-sm font-medium transition-colors ${
                active ? "bg-brand text-white" : "text-white/75 hover:text-white hover:bg-white/5"
              }`}
            >
              <Icon size={17} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="flex-1" />
      <div className="px-5 pb-2 text-xs leading-relaxed text-white/60">
        Production
        <br />
        Engineering
        <br />
        R&amp;D Support
      </div>
      <div className="overflow-hidden">
        <BellowsIllustration className="w-[270px] max-w-none h-auto -ml-6 -mb-3" />
      </div>
    </aside>
  );
}
