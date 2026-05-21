"use client";

import { useEffect } from "react";

export function PWARegistrar() {
  useEffect(() => {
    // 1. Register Service Worker for offline caching
    if (typeof window !== "undefined" && "serviceWorker" in navigator) {
      navigator.serviceWorker
        .register("/sw.js")
        .then((reg) => {
          console.log("[PWA] Service Worker registered with scope:", reg.scope);
        })
        .catch((err) => {
          console.error("[PWA] Service Worker registration failed:", err);
        });
    }

    // 2. Request Push Notification Permission on first load
    if (typeof window !== "undefined" && "Notification" in window) {
      if (Notification.permission === "default") {
        // Delay slightly to prevent jarring UX on immediate mount
        const timer = setTimeout(() => {
          Notification.requestPermission().then((permission) => {
            console.log("[PWA] Push notification permission:", permission);
          });
        }, 1500);
        return () => clearTimeout(timer);
      }
    }
  }, []);

  return null;
}
