"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  House, FileText, SquareCheck, ShoppingCart, Calculator, Factory, Settings, Users,
} from "lucide-react";
import { BrandLogo } from "@/components/Brand";

const NAV = [
  { href: "/", label: "Dashboard", icon: House },
  { href: "/drawings", label: "Drawing Library", icon: FileText },
  { href: "/review", label: "Review Center", icon: SquareCheck },
  { href: "/procurement", label: "Procurement", icon: ShoppingCart },
  { href: "/calculations", label: "Calculations", icon: Calculator },
];

const DIVISIONS = [
  { label: "Production", icon: Factory },
  { label: "Engineering", icon: Settings },
  { label: "R&D Support", icon: Users },
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-[232px] shrink-0 bg-navy text-white flex flex-col sticky top-0 h-screen">
      <div className="px-6 pt-6 pb-8">
        <BrandLogo />
      </div>
      <nav>
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-4 px-6 py-[15px] text-[15px] transition-colors ${
                active ? "bg-brand text-white font-medium" : "text-white/90 hover:bg-white/5"
              }`}
            >
              <Icon size={21} strokeWidth={1.75} />
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="flex-1" />
      <div className="mx-6 border-t border-white/15" />
      <div className="py-4">
        {DIVISIONS.map(({ label, icon: Icon }) => (
          <div key={label} className="flex items-center gap-4 px-7 py-2.5 text-[15px] text-white/90">
            <Icon size={21} strokeWidth={1.75} />
            {label}
          </div>
        ))}
      </div>
    </aside>
  );
}
