"use client";

import Link from "next/link";
import { ChevronRight, Filter } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { PromoArt, HeroArt, BlueprintWatermark } from "@/components/Illustrations";

type Crumb = { label: string; href?: string };

/** Two-column page frame shared by every screen: a left panel (product banner + page-specific
 * categories/filters), and a main column with the blueprint hero banner, content and footer. */
export default function PageLayout({
  aside, title, subtitle, breadcrumb, heroExtra, children,
}: {
  aside: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  breadcrumb?: Crumb[];
  heroExtra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-[calc(100vh-84px)]">
      <aside className="w-[290px] shrink-0 bg-white border-r border-border flex flex-col">
        <div className="relative h-[298px] overflow-hidden">
          <PromoArt className="absolute inset-0 w-full h-full" />
          <div className="relative px-8 pt-6 text-white text-[18px] font-bold leading-[1.25] tracking-wide uppercase">
            Engineered
            <br />
            expansion joints
            <br />
            for a reliable
            <br />
            tomorrow
          </div>
        </div>
        <div className="px-4 py-6 space-y-7">{aside}</div>
      </aside>

      <div className="flex-1 min-w-0 flex flex-col relative">
        <section className="relative h-[178px] overflow-hidden">
          <HeroArt className="absolute inset-0 w-full h-full" />
          <div
            className="absolute right-0 top-0 h-full w-[300px] bg-gradient-to-br from-[#0d3a7d] to-[#1663c2]"
            style={{ clipPath: "polygon(24% 0, 100% 0, 100% 100%, 0 100%)" }}
          >
            <div className="absolute right-8 top-1/2 -translate-y-1/2 text-white text-[17px] font-bold leading-[1.3] tracking-wide uppercase">
              Precision
              <br />
              Engineering
              <br />
              <span className="font-medium">Across industries</span>
              <span className="block w-10 h-[3px] bg-white mt-3" />
            </div>
          </div>
          <div className="relative h-full flex flex-col justify-center pl-11 pr-[340px]">
            {breadcrumb && (
              <div className="flex items-center gap-1.5 text-sm text-steel mb-1">
                {breadcrumb.map((c, i) => (
                  <span key={i} className="flex items-center gap-1.5">
                    {i > 0 && <ChevronRight size={14} className="text-steel-light" />}
                    {c.href ? <Link href={c.href} className="hover:text-accent">{c.label}</Link> : c.label}
                  </span>
                ))}
              </div>
            )}
            <h1 className="page-title truncate">{title}</h1>
            {subtitle && <p className="page-subtitle">{subtitle}</p>}
            {heroExtra}
          </div>
        </section>

        <BlueprintWatermark className="pointer-events-none absolute right-0 bottom-10 w-[520px] opacity-[0.13]" />
        <div className="relative flex-1 px-7 pt-4 pb-8">{children}</div>

        <footer className="relative h-10 bg-[#e9ecf0] border-t border-border flex items-center justify-between px-7 text-[12.5px] text-steel">
          <span>
            © {new Date().getFullYear()} MB Metallic Bellows Pvt Ltd &nbsp;|&nbsp; Engineering Drawing Intelligence &amp; BOM System
          </span>
          <span className="flex gap-6">
            <span>Production</span>
            <span>Engineering</span>
            <span>R&amp;D Support</span>
          </span>
        </footer>
      </div>
    </div>
  );
}

export function AsideSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="px-3 mb-2.5 text-[12px] font-bold uppercase tracking-wider text-steel">{title}</h3>
      {children}
    </section>
  );
}

export function AsideItem({
  icon: Icon, label, count, active, onClick, href,
}: {
  icon?: LucideIcon; label: string; count?: number | string; active?: boolean; onClick?: () => void; href?: string;
}) {
  const cls = `relative w-full flex items-center gap-3.5 px-3.5 py-2.5 rounded-md text-[15px] text-left transition-colors ${
    active ? "bg-brand-light text-graphite font-semibold" : "text-graphite/90 hover:bg-surface"
  }`;
  const inner = (
    <>
      {active && <span className="absolute left-0 top-1 bottom-1 w-[3px] rounded bg-brand" />}
      {Icon && <Icon size={19} strokeWidth={1.75} className={active ? "text-brand" : "text-steel"} />}
      <span className="flex-1 truncate">{label}</span>
      {count !== undefined && <span className="text-[14px] text-graphite/80">{count}</span>}
    </>
  );
  return href ? <Link href={href} className={cls}>{inner}</Link> : <button type="button" onClick={onClick} className={cls}>{inner}</button>;
}

export function AsideSelect({
  label, value, onChange, options,
}: {
  label: string; value: string; onChange: (v: string) => void; options: [string, string][];
}) {
  return (
    <label className="block px-3 mb-3.5">
      <span className="block text-[14px] text-graphite mb-1.5">{label}</span>
      <select className="input !py-2 !text-[14px]" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );
}

export function ClearFiltersButton({ onClick }: { onClick: () => void }) {
  return (
    <div className="px-3">
      <button
        type="button"
        onClick={onClick}
        className="w-full flex items-center justify-center gap-2 border-2 border-graphite rounded-md py-2 text-[15px] font-semibold text-graphite hover:bg-surface"
      >
        <Filter size={17} /> Clear Filters
      </button>
    </div>
  );
}

const TONES = {
  blue: { top: "border-t-brand", head: "bg-[#f2f6fd]", chip: "border-brand text-brand", pill: "bg-brand-light text-brand-dark" },
  orange: { top: "border-t-accent", head: "bg-[#fff6ef]", chip: "border-accent text-accent", pill: "bg-accent-light text-accent-dark" },
  navy: { top: "border-t-navy", head: "bg-[#f1f3f7]", chip: "border-navy text-navy", pill: "bg-[#e3e7ee] text-navy" },
  green: { top: "border-t-[#1fa25c]", head: "bg-[#f0f9f4]", chip: "border-[#1fa25c] text-[#14804a]", pill: "bg-[#dcf3e6] text-[#14804a]" },
};

/** A clearly bounded content block: colored top edge, tinted header bar with a section number, title,
 * optional count and description, then the body. Used to keep stacked sections visually apart. */
export function SectionCard({
  tone = "blue", index, title, count, description, right, children, className = "",
}: {
  tone?: keyof typeof TONES;
  index: string;
  title: string;
  count?: number;
  description?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const t = TONES[tone];
  return (
    <section className={`card overflow-hidden border-t-4 ${t.top} mb-7 ${className}`}>
      <header className={`flex items-center gap-3.5 px-5 py-3.5 border-b border-[#dfe5ec] ${t.head}`}>
        <span className={`w-10 h-10 border-2 flex items-center justify-center shrink-0 font-mono text-[15px] font-bold ${t.chip}`}>
          {index}
        </span>
        <div className="flex-1 min-w-0">
          <h2 className="flex items-center gap-2.5 text-[18px] font-bold text-navy">
            {title}
            {count !== undefined && (
              <span className={`text-[13px] font-semibold px-2.5 py-0.5 rounded-full ${t.pill}`}>{count}</span>
            )}
          </h2>
          {description && <p className="text-[13px] text-steel mt-0.5">{description}</p>}
        </div>
        {right}
      </header>
      {children}
    </section>
  );
}
