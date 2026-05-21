"use client";

import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { AlertTriangle, Loader2 } from "lucide-react";

interface DeactivateConfirmDialogProps {
  isOpen: boolean;
  member: any;
  onClose: () => void;
  onSuccess: () => void;
}

export function DeactivateConfirmDialog({ isOpen, member, onClose, onSuccess }: DeactivateConfirmDialogProps) {
  const { accessToken } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen || !member) return null;

  const handleDeactivate = async () => {
    setIsSubmitting(true);
    setError(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const res = await fetch(`${API_URL}/users/${member.id}/deactivate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to deactivate team member");
      }

      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 font-sans text-slate-100 animate-in fade-in duration-200">
      <div 
        className="w-full max-w-md bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col gap-4 animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-bold text-white">Deactivate Team Member</h2>

        {error && (
          <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
            {error}
          </div>
        )}

        <p className="text-sm text-slate-355 leading-relaxed">
          Are you sure you want to deactivate <strong>{member.full_name || member.email}</strong>?
        </p>
        
        <div className="flex gap-3 p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl items-start">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <span className="text-xs text-amber-200 leading-relaxed">
            Deactivating this user will revoke their login access immediately. Their historical data and assignments will remain intact.
          </span>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-900 hover:bg-slate-850 border border-slate-800 text-slate-300 font-semibold text-xs rounded-xl cursor-pointer transition disabled:opacity-50"
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleDeactivate}
            className="px-4 py-2 bg-red-600 hover:bg-red-500 active:scale-[0.99] text-white font-semibold text-xs rounded-xl cursor-pointer shadow-lg shadow-red-600/20 transition flex items-center gap-1.5 disabled:opacity-50"
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Deactivating...
              </>
            ) : (
              "Deactivate"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
