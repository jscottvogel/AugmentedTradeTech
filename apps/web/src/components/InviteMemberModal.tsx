"use client";

import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { X, Loader2, Mail, Phone, Users } from "lucide-react";

interface InviteMemberModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function InviteMemberModal({ isOpen, onClose, onSuccess }: InviteMemberModalProps) {
  const { accessToken } = useAuth();
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState("tech");
  const [trades, setTrades] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleTradeToggle = (trade: string) => {
    if (trades.includes(trade)) {
      setTrades(trades.filter((t) => t !== trade));
    } else {
      setTrades([...trades, trade]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const res = await fetch(`${API_URL}/users/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          email,
          phone: phone || undefined,
          role,
          trades: role === "tech" ? trades : [],
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to invite team member");
      }

      onSuccess();
      onClose();
      // Reset form
      setEmail("");
      setPhone("");
      setRole("tech");
      setTrades([]);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50 p-4 font-sans text-slate-100 animate-in fade-in duration-200">
      <div 
        className="w-full max-w-md bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
            Invite Team Member
          </h2>
          <button 
            onClick={onClose} 
            className="w-8 h-8 rounded-lg bg-slate-800/40 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 flex items-center justify-center text-slate-400 hover:text-white cursor-pointer transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {error && (
          <div className="p-3 mb-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
              Email Address *
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm disabled:opacity-50"
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
              Phone Number (Optional)
            </label>
            <div className="relative">
              <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 019-2834"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm disabled:opacity-50"
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
              Role
            </label>
            <div className="relative">
              <Users className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm disabled:opacity-50 appearance-none cursor-pointer"
                disabled={isSubmitting}
              >
                <option value="tech">Technician (Magic Link)</option>
                <option value="dispatcher">Dispatcher (Password)</option>
                <option value="company_admin">Admin (Password + MFA)</option>
              </select>
            </div>
          </div>

          {role === "tech" && (
            <div className="space-y-2.5 pt-1">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                Trades Managed
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={trades.includes("hvac")}
                    onChange={() => handleTradeToggle("hvac")}
                    className="w-4 h-4 accent-indigo-500 rounded border-slate-800 bg-slate-950 cursor-pointer focus:ring-indigo-500/50"
                  />
                  HVAC
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={trades.includes("garage_door")}
                    onChange={() => handleTradeToggle("garage_door")}
                    className="w-4 h-4 accent-indigo-500 rounded border-slate-800 bg-slate-950 cursor-pointer focus:ring-indigo-500/50"
                  />
                  Garage Door
                </label>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-900/60">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-slate-900 hover:bg-slate-850 border border-slate-800 text-slate-300 font-semibold text-xs rounded-xl cursor-pointer transition disabled:opacity-50"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-650 hover:bg-indigo-600 active:scale-[0.99] text-white font-semibold text-xs rounded-xl cursor-pointer shadow-lg shadow-indigo-650/20 transition flex items-center gap-1.5 disabled:opacity-50"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Sending...
                </>
              ) : (
                "Send Invitation"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
