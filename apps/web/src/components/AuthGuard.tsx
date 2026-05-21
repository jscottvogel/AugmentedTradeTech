"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../hooks/useAuth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [isLoading, user, router]);

  // Premium loading state during authentication check
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-900 via-slate-950 to-indigo-950 font-sans text-slate-100">
        <div className="flex flex-col items-center p-10 rounded-2xl bg-slate-900/50 backdrop-blur-md border border-slate-800 shadow-2xl">
          <div className="w-12 h-12 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></div>
          <p className="mt-6 text-sm font-medium tracking-wide text-slate-400">
            Securing session...
          </p>
        </div>
      </div>
    );
  }

  // Render children only if authenticated
  return user ? <>{children}</> : null;
}
