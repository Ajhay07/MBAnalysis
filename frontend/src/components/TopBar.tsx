"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const SECTION: Record<string, string> = {
  "/": "Dashboard",
  "/drawings": "Drawing Library",
  "/review": "Review Center",
  "/procurement": "Procurement",
  "/calculations": "Calculations",
};

const ROLE_LABEL: Record<string, string> = {
  admin: "Engineering Admin",
  engineer: "Engineer",
  viewer: "Viewer",
};

function sectionFor(pathname: string | null): string {
  if (!pathname || pathname === "/") return SECTION["/"];
  // Detail pages render their own breadcrumb.
  if (pathname.split("/").filter(Boolean).length > 1) return "";
  const key = Object.keys(SECTION).find((k) => k !== "/" && pathname.startsWith(k));
  return key ? SECTION[key] : "";
}

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
  const initials = name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="flex items-center justify-between px-8 pt-4 pb-1">
      <div className="text-xs text-steel-light">{sectionFor(pathname)}</div>
      <div className="flex items-center gap-4">
        <div className="text-right text-[11px] leading-tight text-steel">
          <div>{now.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</div>
          <div>{now.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</div>
        </div>
        {user && (
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setOpen((o) => !o)}
              className="flex items-center gap-2 pl-4 border-l border-border"
            >
              <span className="w-8 h-8 rounded-full bg-brand text-white text-xs font-semibold flex items-center justify-center">
                {initials}
              </span>
              <span className="text-sm font-medium text-graphite">{name}</span>
              <ChevronDown size={15} className="text-steel" />
            </button>
            {open && (
              <div className="absolute right-0 mt-2 w-56 card py-2 z-50">
                <div className="px-4 pb-2 border-b border-border">
                  <div className="text-xs font-medium text-graphite truncate" title={user.email}>
                    {user.email}
                  </div>
                  <div className="text-[11px] uppercase tracking-wide text-steel-light">{user.role}</div>
                </div>
                <button
                  onClick={logout}
                  className="w-full flex items-center gap-2 px-4 py-2 text-sm text-steel hover:bg-surface hover:text-graphite"
                >
                  <LogOut size={14} /> Log out
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
