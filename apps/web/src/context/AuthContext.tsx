"use client";

import React, { createContext, useState, useEffect, useContext, ReactNode } from "react";
import { useRouter } from "next/navigation";

export interface User {
  id: string;
  email: string;
  role: string;
  full_name: string;
  company_id: string | null;
  is_active: boolean;
  phone?: string | null;
  avatar_url?: string | null;
  tech_profile?: {
    id: string;
    availability_status: string;
    trades: string[];
    certifications: any;
    skills: string[];
    last_heartbeat_at?: string | null;
    status_changed_at?: string | null;
  } | null;
}

export interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
  loginWithPassword: (email: string, password: string, mfaToken?: string) => Promise<void>;
  sendMagicLink: (email: string) => Promise<void>;
  verifyMagicLink: (token: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
  updateCurrentUser: (updatedFields: Partial<User>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Helper to decode JWT client-side without third party library
function decodeJwt(token: string): any {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      window.atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch (error) {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const router = useRouter();

  // Refresh access token silently
  const refreshAccessToken = async (): Promise<string | null> => {
    try {
      const res = await fetch(`${API_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include", // Required to send/receive HTTP-only cookies
      });

      if (!res.ok) {
        throw new Error("Failed to refresh token");
      }

      const data = await res.json();
      setAccessToken(data.access_token);
      setUser(data.user);
      if (typeof window !== "undefined") {
        localStorage.setItem("accessToken", data.access_token);
        localStorage.setItem("user", JSON.stringify(data.user));
      }
      return data.access_token;
    } catch (err) {
      // Fallback: check localStorage in local environments where cookie is blocked/unsupported
      if (typeof window !== "undefined") {
        const storedToken = localStorage.getItem("accessToken");
        const storedUser = localStorage.getItem("user");
        if (storedToken && storedUser) {
          try {
            const parsedUser = JSON.parse(storedUser);
            setAccessToken(storedToken);
            setUser(parsedUser);
            return storedToken;
          } catch (_) {}
        }
        localStorage.removeItem("accessToken");
        localStorage.removeItem("user");
      }
      setAccessToken(null);
      setUser(null);
      return null;
    }
  };

  // Login with Password + MFA
  const loginWithPassword = async (email: string, password: string, mfaToken?: string) => {
    const res = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, mfa_token: mfaToken }),
      credentials: "include",
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || "Invalid login credentials");
    }

    const data = await res.json();
    setAccessToken(data.access_token);
    setUser(data.user);
    if (typeof window !== "undefined") {
      localStorage.setItem("accessToken", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
    }
    router.push("/");
  };

  // Send Magic Link
  const sendMagicLink = async (email: string) => {
    const res = await fetch(`${API_URL}/auth/magic-link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || "Failed to send magic link");
    }
  };

  // Verify Magic Link
  const verifyMagicLink = async (token: string) => {
    const res = await fetch(`${API_URL}/auth/magic-link/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      credentials: "include",
    });

    if (!res.ok) {
      const errorData = await res.json();
      throw new Error(errorData.detail || "Magic link verification failed");
    }

    const data = await res.json();
    setAccessToken(data.access_token);
    setUser(data.user);
    if (typeof window !== "undefined") {
      localStorage.setItem("accessToken", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
    }
    router.push("/");
  };

  // Logout
  const logout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        credentials: "include",
      });
    } catch (err) {
      console.error("Logout request failed:", err);
    } finally {
      setAccessToken(null);
      setUser(null);
      if (typeof window !== "undefined") {
        localStorage.removeItem("accessToken");
        localStorage.removeItem("user");
      }
      router.push("/login");
    }
  };

  // Initial token recovery check on mount
  useEffect(() => {
    const initializeAuth = async () => {
      await refreshAccessToken();
      setIsLoading(false);
    };
    initializeAuth();
  }, []);

  // Periodic silent refresh (runs every 14 minutes to rotate the 15-minute access token)
  useEffect(() => {
    if (!accessToken) return;

    const interval = setInterval(async () => {
      await refreshAccessToken();
    }, 14 * 60 * 1000); // 14 minutes

    return () => clearInterval(interval);
  }, [accessToken]);

  const updateCurrentUser = (updatedFields: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updatedFields } : null));
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isLoading,
        loginWithPassword,
        sendMagicLink,
        verifyMagicLink,
        logout,
        refreshAccessToken,
        updateCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
