"use client";

import React, { useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import { Mail, Lock, ShieldCheck, ArrowLeft, Loader2 } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ScreenState = "EMAIL" | "MAGIC_LINK" | "PASSWORD";

export default function LoginPage() {
  const { loginWithPassword, sendMagicLink } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState("");
  const [screen, setScreen] = useState<ScreenState>("EMAIL");
  const [mfaEnabled, setMfaEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;

    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/auth/lookup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      if (!res.ok) {
        throw new Error("User lookup failed");
      }

      const data = await res.json();
      if (!data.exists) {
        setError("This email address is not registered.");
        setLoading(false);
        return;
      }

      setMfaEnabled(data.mfa_enabled);
      if (data.auth_method === "magic_link") {
        setScreen("MAGIC_LINK");
      } else {
        setScreen("PASSWORD");
      }
    } catch (err: any) {
      setError("An error occurred. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleSendMagicLink = async () => {
    setError(null);
    setLoading(true);
    try {
      await sendMagicLink(email);
      setInfo("Success! We've sent a magic link to your email. Check your inbox.");
    } catch (err: any) {
      setError(err.message || "Failed to send magic link.");
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await loginWithPassword(email, password, mfaToken || undefined);
    } catch (err: any) {
      setError(err.message || "Invalid password or MFA token.");
      setLoading(false);
    }
  };

  const handleBack = () => {
    setScreen("EMAIL");
    setError(null);
    setInfo(null);
    setPassword("");
    setMfaToken("");
  };

  return (
    <div className="flex items-center justify-center min-h-screen px-4 py-12 relative overflow-hidden">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />
      
      <div className="w-full max-w-md p-8 rounded-2xl glass-card border border-white/5 shadow-2xl relative">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500 bg-clip-text text-transparent">
            Augmented Trade Tech
          </h1>
          <p className="text-xs text-slate-400 mt-2 font-medium tracking-wide uppercase">
            Wisdom in every work order
          </p>
        </div>

        {error && (
          <div className="p-4 mb-6 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm leading-relaxed">
            {error}
          </div>
        )}
        {info && (
          <div className="p-4 mb-6 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm leading-relaxed">
            {info}
          </div>
        )}

        {screen === "EMAIL" && (
          <form onSubmit={handleEmailSubmit} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium text-slate-350 block">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="w-full pl-11 pr-4 py-3 rounded-xl glass-input text-slate-200 placeholder-slate-650 focus:outline-none transition-all text-base disabled:opacity-50"
                  disabled={loading}
                />
              </div>
            </div>
            <button
              type="submit"
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-650 to-violet-650 hover:from-indigo-600 hover:to-violet-600 active:scale-[0.99] text-white font-bold text-base transition-all duration-205 shadow-lg shadow-indigo-500/10 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Checking account...
                </>
              ) : (
                "Continue"
              )}
            </button>
          </form>
        )}

        {screen === "MAGIC_LINK" && (
          <div className="space-y-6">
            <p className="text-slate-300 text-center leading-relaxed text-sm">
              Technician account recognized. Click below to receive a secure passwordless login link via email.
            </p>
            {!info && (
              <button
                onClick={handleSendMagicLink}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-650 to-violet-650 hover:from-indigo-600 hover:to-violet-600 active:scale-[0.99] text-white font-bold text-base transition-all duration-205 shadow-lg shadow-indigo-500/10 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Sending link...
                  </>
                ) : (
                  "Send Magic Link"
                )}
              </button>
            )}
            <button
              onClick={handleBack}
              className="w-full py-3 rounded-xl border border-white/5 bg-slate-900/40 hover:bg-slate-805 active:scale-[0.99] text-slate-300 font-bold text-base transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          </div>
        )}

        {screen === "PASSWORD" && (
          <form onSubmit={handlePasswordSubmit} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium text-slate-350 block">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-11 pr-4 py-3 rounded-xl glass-input text-slate-200 placeholder-slate-650 focus:outline-none transition-all text-base disabled:opacity-50"
                  disabled={loading}
                />
              </div>
            </div>

            {mfaEnabled && (
              <div className="space-y-2">
                <label htmlFor="mfaToken" className="text-sm font-medium text-slate-350 block">
                  MFA Code (Authenticator App)
                </label>
                <div className="relative">
                  <ShieldCheck className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                  <input
                    id="mfaToken"
                    type="text"
                    required
                    value={mfaToken}
                    onChange={(e) => setMfaToken(e.target.value)}
                    placeholder="000000"
                    maxLength={6}
                    className="w-full pl-11 pr-4 py-3 rounded-xl glass-input text-slate-200 placeholder-slate-650 focus:outline-none transition-all text-base tracking-widest disabled:opacity-50"
                    disabled={loading}
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              className="w-full py-3 rounded-xl bg-gradient-to-r from-indigo-650 to-violet-650 hover:from-indigo-600 hover:to-violet-600 active:scale-[0.99] text-white font-bold text-base transition-all duration-205 shadow-lg shadow-indigo-500/10 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Authenticating...
                </>
              ) : (
                "Log In"
              )}
            </button>
            <button
              type="button"
              onClick={handleBack}
              className="w-full py-3 rounded-xl border border-white/5 bg-slate-900/40 hover:bg-slate-805 active:scale-[0.99] text-slate-300 font-bold text-base transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              disabled={loading}
            >
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
