"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { BrandLogo } from "@/components/Brand";

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.login(email, password);
      await refresh();
      router.replace("/");
    } catch (err: any) {
      setError("Incorrect email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDemoLogin() {
    setError(null);
    setDemoLoading(true);
    try {
      await api.demoLogin();
      await refresh();
      router.replace("/");
    } catch (err: any) {
      setError("Could not start the demo session. Please try again.");
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="card bg-white p-8 w-full max-w-sm">
        <BrandLogo dark={false} />
        <div className="text-xs text-steel mt-3">Drawing Intelligence &amp; BOM System</div>
        <h1 className="text-lg font-semibold mt-5 mb-1">Sign in</h1>
        <p className="text-sm text-steel mb-5">Log in with your account to continue.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-steel mb-1">Email</label>
            <input
              type="email"
              required
              autoFocus
              className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-steel mb-1">Password</label>
            <input
              type="password"
              required
              className="w-full border border-border rounded-industrial px-3 py-2 text-sm"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial p-2.5">
              {error}
            </div>
          )}
          <button type="submit" className="btn-primary w-full justify-center" disabled={submitting}>
            <LogIn size={16} /> {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="flex items-center gap-3 my-5">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-steel">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <button
          type="button"
          onClick={handleDemoLogin}
          disabled={demoLoading}
          className="w-full justify-center border border-border rounded-industrial px-3 py-2 text-sm font-medium text-steel hover:bg-surface flex items-center gap-2"
        >
          <LogIn size={16} /> {demoLoading ? "Starting demo..." : "Try the demo (read-only)"}
        </button>
        <p className="text-xs text-steel mt-2 text-center">
          Instantly explore the sample projects as a read-only viewer - no account needed. You
          won&apos;t be able to edit, approve, or delete anything.
        </p>
      </div>
    </div>
  );
}
