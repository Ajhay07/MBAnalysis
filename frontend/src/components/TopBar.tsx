"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

const ROLE_LABEL: Record<string, string> = {
  admin: "Engineering Admin",
  engineer: "Engineer",
  viewer: "Viewer",
};

export default function TopBar() {
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
    <div className="flex items-center justify-end gap-5 px-8 pt-4 h-[68px]">
      <span className="text-sm text-steel">{stamp}</span>
      <span className="h-5 w-px bg-steel-light/60" />
      {user && (
        <div className="relative" ref={menuRef}>
          <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-3">
            <span className="w-10 h-10 rounded-full bg-brand text-white text-[15px] font-semibold flex items-center justify-center">
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
  );
}
