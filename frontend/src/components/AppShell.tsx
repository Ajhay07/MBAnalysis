"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { useAuth } from "@/lib/auth-context";

/** Route-protection wrapper: redirects every page except /login to /login when there is no
 * logged-in user, and otherwise renders the normal app chrome (Sidebar + page content). The
 * /login page itself is rendered standalone (no sidebar, no auth requirement) since showing
 * nav for pages the user can't reach yet would be confusing, and gating /login on being logged
 * in would create a redirect loop for a logged-out visitor. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading } = useAuth();
  const router = useRouter();
  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (!loading && !user && !isLoginPage) {
      router.replace("/login");
    }
  }, [loading, user, isLoginPage, router]);

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-steel">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
