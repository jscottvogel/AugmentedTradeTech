"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthContext";
import { triggerBackgroundSync } from "../utils/syncEngine";
import { Wifi, WifiOff, CloudLightning, Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface ConnectivityContextType {
  isOnline: boolean;
  syncStatus: 'idle' | 'syncing' | 'success' | 'error';
  forceSync: () => Promise<void>;
}

const ConnectivityContext = createContext<ConnectivityContextType | undefined>(undefined);

export const useConnectivity = () => {
  const context = useContext(ConnectivityContext);
  if (!context) {
    throw new Error("useConnectivity must be used within a ConnectivityProvider");
  }
  return context;
};

export const ConnectivityProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle');
  const [showConflictToast, setShowConflictToast] = useState<boolean>(false);
  const { accessToken } = useAuth();
  const pathname = usePathname();

  // Listen to custom sync-conflict event
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleSyncConflict = () => {
      setShowConflictToast(true);
    };

    window.addEventListener("sync-conflict", handleSyncConflict);
    return () => {
      window.removeEventListener("sync-conflict", handleSyncConflict);
    };
  }, []);

  // Auto-dismiss conflict toast after 5 seconds
  useEffect(() => {
    if (showConflictToast) {
      const timer = setTimeout(() => {
        setShowConflictToast(false);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [showConflictToast]);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // 1. Connectivity Ping logic
  const checkConnectivity = async () => {
    if (typeof window === "undefined") return;
    if (!navigator.onLine) {
      setIsOnline(false);
      return;
    }

    try {
      // Small cache-busting request to check actual internet capability
      const res = await fetch(`${API_URL}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(4000) // 4 second timeout
      });
      // Any response or even unauthorized status indicates we are connected to the network
      setIsOnline(true);
    } catch (err) {
      console.warn("[Connectivity] Ping to API failed. Set status to offline.");
      setIsOnline(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;

    // Listen to browser network state changes
    const handleOnline = () => {
      console.log("[Connectivity] Browser reported ONLINE");
      checkConnectivity();
    };

    const handleOffline = () => {
      console.log("[Connectivity] Browser reported OFFLINE");
      setIsOnline(false);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    // Initial check
    checkConnectivity();

    // Setup 30s ping timer
    const pingInterval = setInterval(checkConnectivity, 30 * 1000);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      clearInterval(pingInterval);
    };
  }, [accessToken]);

  // 2. Automatically trigger background sync when coming online
  useEffect(() => {
    if (isOnline && accessToken) {
      forceSync();
    }
  }, [isOnline, accessToken]);

  const forceSync = async () => {
    if (!accessToken) return;
    try {
      await triggerBackgroundSync(accessToken, (state) => {
        setSyncStatus(state);
      });
    } catch (err) {
      console.error("[Connectivity] Sync trigger failed:", err);
    }
  };

  // Hide sync status after a short delay on success
  useEffect(() => {
    if (syncStatus === 'success') {
      const timer = setTimeout(() => {
        setSyncStatus('idle');
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [syncStatus]);

  // Check routing to apply portal vs. ATT branding
  const isPortalRoute = pathname?.startsWith("/portal");

  return (
    <ConnectivityContext.Provider value={{ isOnline, syncStatus, forceSync }}>
      {children}

      {/* Floating Status Banners */}
      <div className="fixed top-4 left-1/2 -translate-x-1/2 w-[calc(100%-32px)] max-w-[448px] z-[9999] flex flex-col gap-2 pointer-events-none">
        
        {/* Offline Banner */}
        {!isOnline && (
          <div className="flex items-center gap-3 px-4 py-3 bg-slate-900/85 backdrop-blur-md border border-amber-500/25 rounded-xl shadow-xl text-amber-400 animate-in fade-in slide-in-from-top-4 duration-300">
            <WifiOff className="w-5 h-5 flex-shrink-0 animate-pulse text-amber-500" />
            <div className="flex-1 text-left">
              <p className="text-xs font-bold uppercase tracking-wider">Offline Mode</p>
              <p className="text-[11px] text-slate-300 font-medium leading-normal mt-0.5">
                {isPortalRoute 
                  ? "You are offline. Changes will be saved locally." 
                  : "Offline. Saved to Augmented Trade Tech Local Store."}
              </p>
            </div>
          </div>
        )}

        {/* Syncing Banner */}
        {syncStatus === 'syncing' && (
          <div className="flex items-center gap-3 px-4 py-3 bg-slate-900/85 backdrop-blur-md border border-indigo-500/25 rounded-xl shadow-xl text-indigo-400 animate-in fade-in slide-in-from-top-4 duration-300">
            <Loader2 className="w-5 h-5 flex-shrink-0 animate-spin text-indigo-500" />
            <div className="flex-1 text-left">
              <p className="text-xs font-bold uppercase tracking-wider">Syncing</p>
              <p className="text-[11px] text-slate-300 font-medium leading-normal mt-0.5">
                {isPortalRoute
                  ? "Syncing your changes..."
                  : "Syncing with Augmented Trade Tech Cloud..."}
              </p>
            </div>
          </div>
        )}

        {/* Sync Success Banner */}
        {syncStatus === 'success' && (
          <div className="flex items-center gap-3 px-4 py-3 bg-slate-900/85 backdrop-blur-md border border-emerald-500/25 rounded-xl shadow-xl text-emerald-400 animate-in fade-in slide-in-from-top-4 duration-300">
            <CheckCircle2 className="w-5 h-5 flex-shrink-0 text-emerald-500" />
            <div className="flex-1 text-left">
              <p className="text-xs font-bold uppercase tracking-wider">Sync Complete</p>
              <p className="text-[11px] text-slate-300 font-medium leading-normal mt-0.5">
                {isPortalRoute
                  ? "Sync complete!"
                  : "Sync complete! Data is up to date."}
              </p>
            </div>
          </div>
        )}

        {/* Sync Error Banner */}
        {syncStatus === 'error' && (
          <div className="flex items-center gap-3 px-4 py-3 bg-slate-900/85 backdrop-blur-md border border-red-500/25 rounded-xl shadow-xl text-red-400 animate-in fade-in slide-in-from-top-4 duration-300">
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500 animate-bounce" />
            <div className="flex-1 text-left">
              <p className="text-xs font-bold uppercase tracking-wider">Sync Delayed</p>
              <p className="text-[11px] text-slate-300 font-medium leading-normal mt-0.5">
                Some changes could not be synced. Retrying in background.
              </p>
            </div>
          </div>
        )}

        {/* Conflict Toast */}
        {showConflictToast && (
          <div className="flex items-center gap-3 px-4 py-3 bg-slate-900/85 backdrop-blur-md border border-amber-500/25 rounded-xl shadow-xl text-amber-400 animate-in fade-in slide-in-from-top-4 duration-300 pointer-events-auto cursor-pointer" onClick={() => setShowConflictToast(false)}>
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-amber-500" />
            <div className="flex-1 text-left">
              <p className="text-xs font-bold uppercase tracking-wider">Sync Notice</p>
              <p className="text-[11px] text-slate-300 font-medium leading-normal mt-0.5">
                Some changes were updated by the server
              </p>
            </div>
          </div>
        )}
      </div>
    </ConnectivityContext.Provider>
  );
};
