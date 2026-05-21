"use client";

import React, { useState, useEffect } from "react";
import { 
  ShieldCheck, 
  Wrench, 
  Calendar, 
  Check, 
  Clock, 
  Award, 
  Loader2 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Plan {
  id: string;
  name: string;
  description: string;
  monthly_price_cents: number;
  annual_price_cents: number;
  labor_discount_pct: number;
  parts_discount_pct: number;
  priority_scheduling: boolean;
}

interface ActiveMembership {
  status: "active";
  membership_id: string;
  billing_cadence: string;
  current_period_start: string;
  current_period_end: string;
  enrolled_at: string;
  next_renewal_at: string | null;
  plan: {
    id: string;
    name: string;
    description: string;
    labor_discount_pct: number;
    parts_discount_pct: number;
    priority_scheduling: boolean;
  };
}

interface InactiveMembership {
  status: "none";
  available_plans: Plan[];
}

type MembershipResponse = ActiveMembership | InactiveMembership;

export default function PortalMembershipPage() {
  const { accessToken } = usePortalAuth();
  
  const [membershipData, setMembershipData] = useState<MembershipResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [billingCadence, setBillingCadence] = useState<"monthly" | "annual">("monthly");
  const [enrollingPlanId, setEnrollingPlanId] = useState<string | null>(null);

  const fetchMembership = async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_URL}/portal/membership`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMembershipData(data);
      }
    } catch (err) {
      console.error("Failed to fetch membership info", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMembership();
  }, [accessToken]);

  const handleEnroll = async (planId: string) => {
    if (!accessToken) return;
    setEnrollingPlanId(planId);
    
    try {
      const res = await fetch(`${API_URL}/portal/membership/enroll`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          plan_id: planId,
          billing_cadence: billingCadence
        })
      });

      if (res.ok) {
        // Reload membership state
        await fetchMembership();
      } else {
        const errData = await res.json();
        alert(errData.detail || "Enrollment failed");
      }
    } catch (err) {
      console.error("Error enrolling in membership plan", err);
      alert("An unexpected error occurred during enrollment.");
    } finally {
      setEnrollingPlanId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
      </div>
    );
  }

  const isActive = membershipData?.status === "active";

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-white">Membership Plans</h1>
        <p className="text-slate-400 text-sm">Access exclusive benefits, priority support, and discount structures.</p>
      </div>

      {isActive ? (
        // Active Membership Screen
        <div className="space-y-6">
          {/* Active Card */}
          <div className="p-8 rounded-2xl glass-card border border-white/5 relative overflow-hidden flex flex-col sm:flex-row justify-between gap-6 items-start sm:items-center">
            {/* Ambient glows */}
            <div className="absolute top-0 right-0 w-60 h-60 bg-[var(--primary-color)]/10 rounded-full blur-3xl pointer-events-none" />
            
            <div className="space-y-3 relative z-10">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  Active Member
                </span>
                <span className="text-[10px] font-extrabold uppercase px-2.5 py-1 rounded bg-slate-800 text-slate-300">
                  {(membershipData as ActiveMembership).billing_cadence} Billing
                </span>
              </div>
              <h2 className="text-3xl font-extrabold text-white">
                {(membershipData as ActiveMembership).plan.name}
              </h2>
              <p className="text-slate-400 text-sm max-w-md">
                {(membershipData as ActiveMembership).plan.description}
              </p>
            </div>
            <div className="h-16 w-16 bg-[var(--primary-color)]/10 rounded-full flex items-center justify-center text-[var(--primary-color)] relative z-10">
              <ShieldCheck className="h-8 w-8" />
            </div>
          </div>

          {/* Benefits Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl glass-card border border-white/5 space-y-2">
              <span className="text-slate-550 text-[10px] font-bold uppercase tracking-wider block">Labor Discount</span>
              <h3 className="text-2xl font-bold text-white">
                {(membershipData as ActiveMembership).plan.labor_discount_pct}% Off
              </h3>
              <p className="text-xs text-slate-400">Discount automatically applied to all repair services.</p>
            </div>

            <div className="p-6 rounded-2xl glass-card border border-white/5 space-y-2">
              <span className="text-slate-550 text-[10px] font-bold uppercase tracking-wider block">Parts Discount</span>
              <h3 className="text-2xl font-bold text-white">
                {(membershipData as ActiveMembership).plan.parts_discount_pct}% Off
              </h3>
              <p className="text-xs text-slate-400">Discount automatically applied to all equipment parts.</p>
            </div>

            <div className="p-6 rounded-2xl glass-card border border-white/5 space-y-2">
              <span className="text-slate-550 text-[10px] font-bold uppercase tracking-wider block">Priority Support</span>
              <h3 className="text-2xl font-bold text-white">
                {(membershipData as ActiveMembership).plan.priority_scheduling ? "Enabled" : "Standard"}
              </h3>
              <p className="text-xs text-slate-400">Enjoy priority queue status for scheduling service requests.</p>
            </div>
          </div>

          {/* Renewal details */}
          <div className="p-5 rounded-xl border border-white/5 bg-white/[0.005] text-slate-400 text-sm space-y-3">
            <h4 className="text-white font-bold flex items-center gap-1 text-xs uppercase tracking-wider">
              <Clock className="h-4 w-4 text-[var(--primary-color)]" />
              Subscription Status
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div>
                <span>Enrolled Date:</span>
                <span className="text-white font-semibold ml-1.5">
                  {new Date((membershipData as ActiveMembership).enrolled_at).toLocaleDateString()}
                </span>
              </div>
              <div>
                <span>Renewal / Expiration Date:</span>
                <span className="text-white font-semibold ml-1.5">
                  {(membershipData as ActiveMembership).next_renewal_at
                    ? new Date((membershipData as ActiveMembership).next_renewal_at!).toLocaleDateString()
                    : "N/A"}
                </span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        // Inactive Enrollment Screen
        <div className="space-y-6">
          
          {/* Billing Toggle */}
          <div className="flex justify-center">
            <div className="p-1 rounded-xl bg-slate-900 border border-white/5 flex gap-1 text-xs">
              <button
                onClick={() => setBillingCadence("monthly")}
                className={`px-4 py-2 rounded-lg font-bold transition-all cursor-pointer ${
                  billingCadence === "monthly" 
                    ? "bg-[var(--primary-color)] text-white" 
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Monthly Billing
              </button>
              <button
                onClick={() => setBillingCadence("annual")}
                className={`px-4 py-2 rounded-lg font-bold transition-all cursor-pointer ${
                  billingCadence === "annual" 
                    ? "bg-[var(--primary-color)] text-white" 
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Annual (Save ~10%)
              </button>
            </div>
          </div>

          {/* Available Plans Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {(membershipData as InactiveMembership).available_plans.map(plan => {
              const price = billingCadence === "monthly" ? plan.monthly_price_cents : plan.annual_price_cents;
              return (
                <div key={plan.id} className="rounded-2xl glass-card border border-white/5 p-6 flex flex-col justify-between space-y-6">
                  
                  <div className="space-y-4">
                    <div>
                      <h3 className="text-xl font-bold text-white">{plan.name}</h3>
                      <p className="text-xs text-slate-400 mt-1">{plan.description}</p>
                    </div>

                    <div className="flex items-baseline gap-1.5">
                      <span className="text-3xl font-extrabold text-white">${(price / 100).toFixed(2)}</span>
                      <span className="text-slate-500 text-xs font-semibold capitalize">/ {billingCadence}</span>
                    </div>

                    {/* Benefit Bullets */}
                    <div className="space-y-2 border-t border-white/5 pt-4 text-sm text-slate-300">
                      <div className="flex items-center gap-2">
                        <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                        <span><strong>{plan.labor_discount_pct}% Off</strong> Labor charges</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                        <span><strong>{plan.parts_discount_pct}% Off</strong> Repair parts</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                        <span>
                          {plan.priority_scheduling 
                            ? "Priority scheduling enabled" 
                            : "Standard scheduling support"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => handleEnroll(plan.id)}
                    disabled={enrollingPlanId !== null}
                    className="w-full py-2.5 rounded-xl hover:opacity-95 text-white font-bold text-sm transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                    style={{ backgroundColor: "var(--primary-color)" }}
                  >
                    {enrollingPlanId === plan.id ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Enrolling...
                      </>
                    ) : (
                      "Subscribe & Activate"
                    )}
                  </button>

                </div>
              );
            })}
          </div>

        </div>
      )}
    </div>
  );
}
