"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="card bg-white p-8 w-full max-w-sm">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-7 h-7 rounded-industrial bg-accent flex items-center justify-center text-white font-bold text-sm">
            E
          </div>
          <div className="text-sm font-semibold">Drawing Intelligence &amp; BOM System</div>
        </div>
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
      </div>
    </div>
  );
}
