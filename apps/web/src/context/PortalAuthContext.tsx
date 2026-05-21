"use client";

import React, { createContext, useState, useEffect, useContext, ReactNode } from "react";
import { useRouter } from "next/navigation";

export interface Customer {
  id: string;
  email: string;
  phone: string;
  first_name: string;
  last_name: string;
  company_id: string;
}

export interface PortalAuthContextType {
  customer: Customer | null;
  accessToken: string | null;
  isLoading: boolean;
  sendMagicLink: (contact: string) => Promise<void>;
  verifyMagicLink: (token: string) => Promise<Customer>;
  logout: () => Promise<void>;
}

const PortalAuthContext = createContext<PortalAuthContextType | undefined>(undefined);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  // Load auth state from localStorage on mount
  useEffect(() => {
    const initializeAuth = () => {
      if (typeof window !== "undefined") {
        const storedToken = localStorage.getItem("portal_accessToken");
        const storedCustomer = localStorage.getItem("portal_customer");
        if (storedToken && storedCustomer) {
          try {
            setAccessToken(storedToken);
            setCustomer(JSON.parse(storedCustomer));
          } catch (_) {
            localStorage.removeItem("portal_accessToken");
            localStorage.removeItem("portal_customer");
          }
        }
      }
      setIsLoading(false);
    };
    initializeAuth();
  }, []);

  // Send Magic Link
  const sendMagicLink = async (contact: string) => {
    const res = await fetch(`${API_URL}/portal/auth/magic-link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contact }),
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || "Failed to send magic link");
    }
  };

  // Verify Magic Link
  const verifyMagicLink = async (token: string): Promise<Customer> => {
    const res = await fetch(`${API_URL}/portal/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || "Magic link verification failed");
    }

    const data = await res.json();
    setAccessToken(data.access_token);
    setCustomer(data.customer);

    if (typeof window !== "undefined") {
      localStorage.setItem("portal_accessToken", data.access_token);
      localStorage.setItem("portal_customer", JSON.stringify(data.customer));
    }
    return data.customer;
  };

  // Logout
  const logout = async () => {
    setAccessToken(null);
    setCustomer(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem("portal_accessToken");
      localStorage.removeItem("portal_customer");
    }
    router.push("/portal/login");
  };

  return (
    <PortalAuthContext.Provider
      value={{
        customer,
        accessToken,
        isLoading,
        sendMagicLink,
        verifyMagicLink,
        logout,
      }}
    >
      {children}
    </PortalAuthContext.Provider>
  );
}

export function usePortalAuth() {
  const context = useContext(PortalAuthContext);
  if (context === undefined) {
    throw new Error("usePortalAuth must be used within a PortalAuthProvider");
  }
  return context;
}
