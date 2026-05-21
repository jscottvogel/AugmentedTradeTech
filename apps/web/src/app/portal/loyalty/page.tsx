"use client";

import React, { useState, useEffect } from "react";
import { 
  Award, 
  Sparkles, 
  History, 
  PlusCircle, 
  MinusCircle, 
  HelpCircle, 
  Loader2 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface LedgerEntry {
  id: string;
  entry_type: string;
  points: number;
  description: string;
  created_at: string;
}

interface LoyaltyData {
  balance: number;
  lifetime_earned: number;
  history: LedgerEntry[];
}

export default function PortalLoyaltyPage() {
  const { accessToken } = usePortalAuth();
  
  const [loyaltyData, setLoyaltyData] = useState<LoyaltyData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;

    const fetchLoyalty = async () => {
      try {
        const res = await fetch(`${API_URL}/portal/loyalty`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const data = await res.json();
          setLoyaltyData(data);
        }
      } catch (err) {
        console.error("Failed to fetch loyalty data", err);
      } finally {
        setLoading(false);
      }
    };

    fetchLoyalty();
  }, [accessToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
      </div>
    );
  }

  const balance = loyaltyData?.balance || 0;
  const lifetimeEarned = loyaltyData?.lifetime_earned || 0;
  const history = loyaltyData?.history || [];

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white">Loyalty Rewards</h1>
        <p className="text-slate-400 text-sm">Earn points on every service call and redeem them for future repair credits.</p>
      </div>

      {/* Top Banner and Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Available Points Balance */}
        <div className="p-6 rounded-2xl glass-card border border-white/5 md:col-span-2 relative overflow-hidden flex flex-col justify-between min-h-[160px]">
          <div className="absolute top-0 right-0 w-48 h-48 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
          <div className="space-y-1.5 z-10">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Available Balance</span>
            <div className="flex items-center gap-2">
              <h2 className="text-4xl font-extrabold text-white">{balance}</h2>
              <Sparkles className="h-5 w-5 text-emerald-400 animate-pulse" />
            </div>
            <p className="text-xs text-slate-400">Equivalent to ${(balance / 100).toFixed(2)} in service credits.</p>
          </div>
          <p className="text-xs text-slate-400 mt-4 leading-relaxed z-10">
            To redeem points, simply inform your technician at the time of invoice adjustments, or apply them towards active invoices online.
          </p>
        </div>

        {/* Lifetime Earned */}
        <div className="p-6 rounded-2xl glass-card border border-white/5 flex flex-col justify-between min-h-[160px]">
          <div className="space-y-1.5">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Lifetime Points Earned</span>
            <h2 className="text-4xl font-extrabold text-slate-200">{lifetimeEarned}</h2>
            <p className="text-xs text-slate-500">Total accumulated rewards.</p>
          </div>
          <div className="h-10 w-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500 self-end">
            <Award className="h-6 w-6" />
          </div>
        </div>

      </div>

      {/* Transaction History Section */}
      <div className="space-y-4">
        <h3 className="text-lg font-bold text-white flex items-center gap-2">
          <History className="h-4.5 w-4.5 text-[var(--primary-color)]" />
          Transaction History
        </h3>

        {history.length === 0 ? (
          <div className="p-12 rounded-2xl glass-card border border-white/5 text-center text-slate-500">
            No transaction records found. Points are awarded upon invoice payments.
          </div>
        ) : (
          <div className="border border-white/5 rounded-2xl overflow-hidden glass-card">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-white/5 bg-white/[0.01]">
                    <th className="p-4 font-semibold text-slate-400">Transaction ID</th>
                    <th className="p-4 font-semibold text-slate-400">Description</th>
                    <th className="p-4 font-semibold text-slate-400">Date</th>
                    <th className="p-4 font-semibold text-slate-400 text-right">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map(entry => {
                    const isEarn = entry.entry_type.toLowerCase() === "earn";
                    return (
                      <tr key={entry.id} className="border-b border-white/5 last:border-b-0 hover:bg-white/[0.005]">
                        <td className="p-4 font-mono text-xs text-slate-500">{entry.id}</td>
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            {isEarn ? (
                              <PlusCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                            ) : (
                              <MinusCircle className="h-4 w-4 text-amber-400 shrink-0" />
                            )}
                            <span className="font-medium text-white">{entry.description}</span>
                          </div>
                        </td>
                        <td className="p-4 text-slate-400">
                          {new Date(entry.created_at).toLocaleString()}
                        </td>
                        <td className={`p-4 text-right font-bold ${
                          isEarn ? "text-emerald-400" : "text-amber-400"
                        }`}>
                          {isEarn ? `+${entry.points}` : `-${entry.points}`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Rewards Info Box */}
      <div className="p-5 rounded-xl border border-white/5 bg-white/[0.005] flex gap-3 text-sm">
        <HelpCircle className="h-5 w-5 text-[var(--primary-color)] shrink-0 mt-0.5" />
        <div className="space-y-1 leading-relaxed">
          <h4 className="text-white font-bold text-xs uppercase tracking-wider">How are points calculated?</h4>
          <p className="text-xs text-slate-400">
            For every dollar you spend paying service invoices, you earn 1 loyalty point (excluding taxes, discounts, and fees). When you redeem points, 100 points corresponds to $1.00 off your service invoice. Redemptions can be processed by technician staff or online.
          </p>
        </div>
      </div>

    </div>
  );
}
