import Link from "next/link";
import { ChevronRight } from "lucide-react";

type Crumb = { label: string; href?: string };

export default function PageHeader({
  breadcrumb, title, subtitle, actions, children,
}: {
  breadcrumb: Crumb[];
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-7">
      <div className="flex items-center gap-1.5 text-sm text-steel mb-2">
        {breadcrumb.map((c, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={14} className="text-steel-light" />}
            {c.href ? <Link href={c.href} className="hover:text-brand">{c.label}</Link> : c.label}
          </span>
        ))}
      </div>
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="page-title">{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
          {children}
        </div>
        {actions && <div className="flex items-center gap-3 shrink-0 pt-1">{actions}</div>}
      </div>
    </div>
  );
}
