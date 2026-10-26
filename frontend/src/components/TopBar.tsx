"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { BrandLogo } from "@/components/Brand";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/drawings", label: "Drawing Library" },
  { href: "/review", label: "Review Center" },
  { href: "/procurement", label: "Procurement" },
  { href: "/indents", label: "Indent Sheets" },
  { href: "/calculations", label: "Calculations" },
];

const ROLE_LABEL: Record<string, string> = {
  admin: "Engineering Admin",
  engineer: "Engineer",
  viewer: "Viewer",
};

export default function TopBar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [now, setNow] = useState(() => new Date());
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const name = user ? ROLE_LABEL[user.role] || user.role : "";
  const initials = name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const stamp = `${now.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}, ${now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}`;

  return (
    <header className="sticky top-0 z-40 h-[84px] bg-white flex items-stretch border-b border-border shadow-[0_1px_3px_rgba(15,35,64,0.05)]">
      <div className="w-[290px] shrink-0 flex items-center px-11">
        <BrandLogo dark={false} />
      </div>
      <nav className="flex items-stretch gap-1 pl-6">
        {NAV.map((item) => {
          const active = pathname === item.href || (item.href !== "/" && pathname?.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`relative flex items-center px-6 text-[15px] font-medium transition-colors ${
                active ? "text-accent" : "text-graphite hover:text-accent"
              }`}
            >
              {item.label}
              {active && <span className="absolute left-3 right-3 bottom-0 h-[3px] rounded-t bg-accent" />}
            </Link>
          );
        })}
      </nav>
      <div className="flex-1 flex items-center justify-end gap-6 px-8">
        <span className="text-[14px] text-steel">{stamp}</span>
        <span className="h-9 w-px bg-border" />
        {user && (
          <div className="relative" ref={menuRef}>
            <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-3">
              <span className="w-10 h-10 rounded-full bg-navy text-white text-[15px] font-semibold flex items-center justify-center">
                {initials}
              </span>
              <span className="text-[15px] font-medium text-graphite">{name}</span>
              <ChevronDown size={18} className="text-graphite" />
            </button>
            {open && (
              <div className="absolute right-0 mt-2 w-60 card py-2 z-50">
                <div className="px-4 pb-2 border-b border-border">
                  <div className="text-sm font-medium text-graphite truncate" title={user.email}>{user.email}</div>
                  <div className="text-xs uppercase tracking-wide text-steel-light">{user.role}</div>
                </div>
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-steel hover:bg-surface hover:text-graphite"
                >
                  <LogOut size={15} /> Log out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
