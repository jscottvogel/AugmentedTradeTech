"use client";

import React, { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

export default function PortalVerifyPage() {
  const { verifyMagicLink, accessToken } = usePortalAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const performVerification = async () => {
      const token = searchParams.get("token");
      const slug = searchParams.get("slug") || searchParams.get("company");
      
      if (slug) {
        localStorage.setItem("portal_company_slug", slug);
      }

      if (!token) {
        setError("No login token provided. Please request a new link.");
        return;
      }

      try {
        await verifyMagicLink(token);
        router.push("/portal/home");
      } catch (err: any) {
        setError(err.message || "Failed to verify login link. It may have expired or been used already.");
      }
    };

    performVerification();
  }, [searchParams, verifyMagicLink, router]);

  return (
    <div className="flex items-center justify-center min-h-[60vh] px-4 py-12">
      <div className="w-full max-w-md p-8 rounded-2xl glass-card border border-white/5 shadow-2xl text-center">
        {error ? (
          <div>
            <h3 className="text-xl font-bold text-red-400 mb-4">Verification Failed</h3>
            <p className="text-slate-350 text-sm mb-6 leading-relaxed">{error}</p>
            <button
              onClick={() => router.push("/portal/login")}
              className="px-6 py-2.5 rounded-xl text-white font-semibold transition-all"
              style={{ backgroundColor: "var(--primary-color)" }}
            >
              Back to Login
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center space-y-4">
            <Loader2 className="h-10 w-10 animate-spin text-[var(--primary-color)]" />
            <h3 className="text-xl font-semibold text-white">Verifying Login Link</h3>
            <p className="text-slate-400 text-sm">Please wait while we log you in...</p>
          </div>
        )}
      </div>
    </div>
  );
}
