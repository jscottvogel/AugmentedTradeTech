"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Mail, Phone, Loader2, Send } from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PortalLoginPage() {
  const { sendMagicLink, accessToken } = usePortalAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const [contact, setContact] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState<string>("Customer Portal");

  // Fetch company config just to show the company name on the login card
  useEffect(() => {
    if (accessToken) {
      router.push("/portal/home");
      return;
    }

    const fetchCompanyName = async () => {
      let slug = searchParams.get("slug") || searchParams.get("company");
      if (!slug) {
        slug = localStorage.getItem("portal_company_slug") || "";
      } else {
        localStorage.setItem("portal_company_slug", slug);
      }

      if (!slug) return;

      try {
        const res = await fetch(`${API_URL}/portal/company-config?slug=${slug}`);
        if (res.ok) {
          const data = await res.json();
          if (data.name) {
            setCompanyName(data.name);
          }
        }
      } catch (err) {
        console.error("Failed to load company config", err);
      }
    };

    fetchCompanyName();
  }, [accessToken, searchParams, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contact.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await sendMagicLink(contact.trim());
      setSuccess("We have sent a login link to your email or phone number. Please check your messages!");
    } catch (err: any) {
      setError(err.message || "Failed to send magic link. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[70vh] px-4 py-12 relative">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-[var(--primary-color)]/5 rounded-full blur-3xl pointer-events-none" />
      
      <div className="w-full max-w-md p-8 rounded-2xl glass-card border border-white/5 shadow-2xl relative">
        <div className="text-center mb-8">
          <h2 className="text-3xl font-extrabold tracking-tight text-white">
            Welcome to {companyName}
          </h2>
          <p className="text-slate-400 text-sm mt-3 font-medium">
            Enter your email or phone number to access your customer portal.
          </p>
        </div>

        {error && (
          <div className="p-4 mb-6 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm leading-relaxed">
            {error}
          </div>
        )}

        {success && (
          <div className="p-4 mb-6 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm leading-relaxed">
            {success}
          </div>
        )}

        {!success && (
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="contact" className="text-sm font-medium text-slate-300 block">
                Email Address or Phone Number
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <input
                  id="contact"
                  type="text"
                  required
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  placeholder="name@example.com or 555-0199"
                  className="w-full pl-11 pr-4 py-3 rounded-xl glass-input text-slate-200 placeholder-slate-500 focus:outline-none transition-all text-base disabled:opacity-50"
                  disabled={loading}
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-3 rounded-xl hover:opacity-95 active:scale-[0.99] text-white font-bold text-base transition-all duration-200 shadow-lg flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
              style={{ backgroundColor: "var(--primary-color)", boxShadow: "0 4px 14px 0 rgba(var(--primary-color), 0.3)" }}
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Sending Link...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Send Magic Link
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
