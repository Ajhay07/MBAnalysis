"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, Mail, Lock, Eye, EyeOff, ArrowRight, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { BrandLogo } from "@/components/Brand";
import { PromoArt, BlueprintWatermark } from "@/components/Illustrations";

const CERTS = ["ISO 9001:2015", "ASME U-Stamp", "PED Enabled"];
const FACTS: [string, string][] = [
  ["100 NB – 8 m", "Bellows diameter range"],
  ["SS · Ni · CS", "Stainless, high-nickel, carbon steel"],
  ["30+ yrs", "Design & R&D experience"],
];

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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
    } catch {
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
    } catch {
      setError("Could not start the demo session. Please try again.");
    } finally {
      setDemoLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex bg-white">
      {/* Left: brand showcase */}
      <section className="relative hidden lg:flex w-[52%] overflow-hidden text-white">
        <PromoArt className="absolute inset-0 w-full h-full" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#0b2f66]/70 via-transparent to-[#081d40]/90" />
        <div
          className="absolute inset-0 opacity-[0.08]"
          style={{
            backgroundImage:
              "linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />
        <div className="relative z-10 flex flex-col justify-between w-full p-14">
          <div className="inline-flex self-start rounded-md bg-white/95 px-4 py-3 shadow-lg">
            <BrandLogo dark={false} />
          </div>

          <div className="max-w-[520px]">
            <div className="flex items-center gap-3 mb-5">
              <span className="h-[3px] w-12 bg-accent" />
              <span className="text-[13px] font-semibold uppercase tracking-[0.2em] text-white/80">
                Drawing Intelligence &amp; BOM System
              </span>
            </div>
            <h1 className="text-[46px] leading-[1.08] font-extrabold uppercase tracking-tight">
              Engineered expansion joints
              <br />
              <span className="text-[#7cc6ff]">for a reliable tomorrow</span>
            </h1>
            <p className="mt-5 text-[17px] text-white/80 leading-relaxed">
              Turn engineering drawings into accurate bills of materials, purchase plans and
              shop-floor make lists — in minutes, not days.
            </p>

            <div className="grid grid-cols-3 gap-3 mt-9">
              {FACTS.map(([big, small]) => (
                <div key={big} className="rounded-lg border border-white/15 bg-white/10 backdrop-blur-sm px-4 py-3.5">
                  <div className="text-[20px] font-bold">{big}</div>
                  <div className="text-[12.5px] text-white/70 mt-0.5 leading-snug">{small}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {CERTS.map((c) => (
              <span
                key={c}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/10 px-3.5 py-1.5 text-[13px] font-medium"
              >
                <ShieldCheck size={15} className="text-[#7cc6ff]" /> {c}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Right: sign-in */}
      <section className="relative flex-1 flex flex-col bg-[#f6f8fb]">
        <div
          className="absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "linear-gradient(#dfe6ee 1px, transparent 1px), linear-gradient(90deg, #dfe6ee 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        />
        <BlueprintWatermark className="pointer-events-none absolute -right-10 bottom-6 w-[520px] opacity-[0.16]" />

        <div className="relative flex-1 flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-[440px]">
            <div className="lg:hidden mb-8">
              <BrandLogo dark={false} />
            </div>

            <div className="rounded-2xl bg-white border border-[#d8dfe8] shadow-[0_20px_50px_-20px_rgba(15,35,64,0.35)] overflow-hidden">
              <div className="h-1.5 bg-gradient-to-r from-[#0a8fd8] via-[#1d64c8] to-accent" />
              <div className="p-9">
                <h2 className="text-[30px] font-extrabold text-navy tracking-tight">Welcome back</h2>
                <p className="text-[15px] text-steel mt-1 mb-7">Sign in to your engineering workspace.</p>

                <form onSubmit={handleSubmit} className="space-y-5">
                  <label className="block">
                    <span className="block text-[13px] font-semibold text-graphite mb-1.5">Email</span>
                    <span className="relative block">
                      <Mail size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-steel-light" />
                      <input
                        type="email"
                        required
                        autoFocus
                        placeholder="you@company.com"
                        className="input !h-12 !pl-11"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                      />
                    </span>
                  </label>
                  <label className="block">
                    <span className="block text-[13px] font-semibold text-graphite mb-1.5">Password</span>
                    <span className="relative block">
                      <Lock size={18} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-steel-light" />
                      <input
                        type={showPassword ? "text" : "password"}
                        required
                        placeholder="••••••••"
                        className="input !h-12 !pl-11 !pr-11"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((s) => !s)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-steel-light hover:text-graphite"
                        aria-label={showPassword ? "Hide password" : "Show password"}
                      >
                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </span>
                  </label>

                  {error && (
                    <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-industrial px-3 py-2.5">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={submitting}
                    className="group w-full h-12 inline-flex items-center justify-center gap-2 rounded-industrial bg-navy hover:bg-[#16305a] text-white text-[16px] font-semibold transition-colors disabled:opacity-60"
                  >
                    <LogIn size={18} />
                    {submitting ? "Signing in..." : "Sign in"}
                    {!submitting && <ArrowRight size={18} className="transition-transform group-hover:translate-x-0.5" />}
                  </button>
                </form>

                <div className="flex items-center gap-3 my-6">
                  <div className="h-px flex-1 bg-border" />
                  <span className="text-xs font-medium uppercase tracking-wider text-steel-light">or</span>
                  <div className="h-px flex-1 bg-border" />
                </div>

                <button
                  type="button"
                  onClick={handleDemoLogin}
                  disabled={demoLoading}
                  className="w-full h-12 inline-flex items-center justify-center gap-2 rounded-industrial border-2 border-accent text-accent hover:bg-accent hover:text-white text-[15px] font-semibold transition-colors disabled:opacity-60"
                >
                  {demoLoading ? "Starting demo..." : "Explore the demo (read-only)"}
                </button>
                <p className="text-[12.5px] text-steel mt-3 text-center leading-relaxed">
                  Browse the sample drawings as a viewer — no account needed. Editing, approving and
                  deleting stay disabled.
                </p>
              </div>
            </div>
          </div>
        </div>

        <footer className="relative px-8 py-4 text-[12.5px] text-steel flex justify-between">
          <span>© {new Date().getFullYear()} MB Metallic Bellows Pvt Ltd</span>
          <span>Oragadam, Chennai · mbmetallicbellows.com</span>
        </footer>
      </section>
    </div>
  );
}
