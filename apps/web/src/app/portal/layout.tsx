"use client";

import React, { useState, useEffect, Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { PortalAuthProvider, usePortalAuth } from "../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CompanyConfig {
  name: string;
  logo_url: string | null;
  primary_color: string;
  slug: string;
}

function PortalThemeWrapper({ children }: { children: React.ReactNode }) {
  const { customer, accessToken, logout, isLoading } = usePortalAuth();
  const [config, setConfig] = useState<CompanyConfig | null>(null);
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  // 1. Resolve company slug and fetch configuration
  useEffect(() => {
    const fetchConfig = async () => {
      let slug = searchParams.get("slug") || searchParams.get("company");
      
      if (slug) {
        localStorage.setItem("portal_company_slug", slug);
      } else {
        slug = localStorage.getItem("portal_company_slug") || "";
      }

      try {
        let url = `${API_URL}/portal/company-config`;
        const headers: HeadersInit = {};

        if (slug) {
          url += `?slug=${slug}`;
        } else if (accessToken) {
          headers["Authorization"] = `Bearer ${accessToken}`;
        } else {
          // No way to fetch config yet
          return;
        }

        const res = await fetch(url, { headers });
        if (res.ok) {
          const data = await res.json();
          setConfig(data);
          if (data.slug) {
            localStorage.setItem("portal_company_slug", data.slug);
          }
        }
      } catch (err) {
        console.error("Failed to load company config", err);
      }
    };

    fetchConfig();
  }, [accessToken, searchParams]);

  // 2. Redirect unauthenticated users to login, except on public pages
  useEffect(() => {
    if (isLoading) return;
    
    const isPublicPage = pathname === "/portal/login" || pathname === "/portal/verify";
    if (!accessToken && !isPublicPage) {
      router.push("/portal/login");
    }
  }, [accessToken, pathname, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950 text-white">
        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const isPublicPage = pathname === "/portal/login" || pathname === "/portal/verify";
  const primaryColor = config?.primary_color || "#3b82f6";

  return (
    <div 
      className="min-h-screen flex flex-col bg-gray-950 text-gray-100"
      style={{ "--primary-color": primaryColor } as React.CSSProperties}
    >
      {/* Header */}
      <header className="sticky top-0 z-40 w-full glass-card border-b border-white/5 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          {config?.logo_url ? (
            <img 
              src={config.logo_url} 
              alt={config.name} 
              className="h-9 w-auto max-w-[150px] object-contain rounded-md" 
            />
          ) : (
            <div 
              className="h-9 w-9 rounded-lg flex items-center justify-center font-bold text-lg text-white"
              style={{ backgroundColor: primaryColor }}
            >
              {config?.name?.[0] || "C"}
            </div>
          )}
          <span className="font-semibold text-lg tracking-tight">{config?.name || "Customer Portal"}</span>
        </div>

        {/* Navigation Links for Logged In Customers */}
        {accessToken && !isPublicPage && (
          <nav className="hidden md:flex items-center space-x-6">
            <Link 
              href="/portal/home" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/home" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Home
            </Link>
            <Link 
              href="/portal/history" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/history" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              History
            </Link>
            <Link 
              href="/portal/invoices" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/invoices" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Invoices
            </Link>
            <Link 
              href="/portal/equipment" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/equipment" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Equipment
            </Link>
            <Link 
              href="/portal/request" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/request" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Request Service
            </Link>
            <Link 
              href="/portal/membership" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/membership" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Membership
            </Link>
            <Link 
              href="/portal/loyalty" 
              className={`text-sm font-medium transition-colors hover:text-[var(--primary-color)] ${
                pathname === "/portal/loyalty" ? "text-[var(--primary-color)]" : "text-gray-400"
              }`}
            >
              Loyalty Rewards
            </Link>
          </nav>
        )}

        {/* Action Button */}
        {accessToken && !isPublicPage ? (
          <div className="flex items-center space-x-4">
            <span className="hidden sm:inline text-xs text-gray-400">
              Welcome, {customer?.first_name}
            </span>
            <button 
              onClick={logout}
              className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-white/10 hover:border-red-500/30 hover:text-red-400 transition-all cursor-pointer"
            >
              Logout
            </button>
          </div>
        ) : (
          <div />
        )}
      </header>

      {/* Mobile Nav Bar */}
      {accessToken && !isPublicPage && (
        <div className="md:hidden w-full glass-card border-b border-white/5 py-3 px-6 flex items-center justify-around overflow-x-auto gap-2">
          <Link href="/portal/home" className="text-xs font-medium text-gray-400 hover:text-white">Home</Link>
          <Link href="/portal/history" className="text-xs font-medium text-gray-400 hover:text-white">History</Link>
          <Link href="/portal/invoices" className="text-xs font-medium text-gray-400 hover:text-white">Invoices</Link>
          <Link href="/portal/equipment" className="text-xs font-medium text-gray-400 hover:text-white">Equipment</Link>
          <Link href="/portal/request" className="text-xs font-medium text-gray-400 hover:text-white">Request</Link>
          <Link href="/portal/membership" className="text-xs font-medium text-gray-400 hover:text-white">Membership</Link>
          <Link href="/portal/loyalty" className="text-xs font-medium text-gray-400 hover:text-white">Loyalty</Link>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-grow max-w-7xl w-full mx-auto p-4 md:p-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="py-6 border-t border-white/5 text-center text-xs text-gray-500">
        &copy; {new Date().getFullYear()} {config?.name || "Customer Service Portal"}. All rights reserved.
      </footer>
    </div>
  );
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <PortalAuthProvider>
      <Suspense fallback={
        <div className="min-h-screen flex items-center justify-center bg-gray-950 text-white">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      }>
        <PortalThemeWrapper>{children}</PortalThemeWrapper>
      </Suspense>
    </PortalAuthProvider>
  );
}
