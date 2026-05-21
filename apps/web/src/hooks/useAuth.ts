"use client";

import { useAuth as useAuthFromContext } from "../context/AuthContext";

export function useAuth() {
  return useAuthFromContext();
}
