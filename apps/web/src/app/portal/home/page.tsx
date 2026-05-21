"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { 
  FileText, 
  Wrench, 
  Award, 
  ArrowRight, 
  Calendar, 
  CreditCard, 
  Sparkles, 
  Loader2 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Job {
  id: string;
  job_number: string;
  trade: string;
  job_type: string;
  priority: string;
  status: string;
  reported_problem: string;
  completed_at: string | null;
}

interface Invoice {
  id: string;
  invoice_number: string;
  status: string;
  total_cents: number;
  balance_cents: number;
  due_date: string | null;
}

export default function PortalHomePage() {
  const { customer, accessToken } = usePortalAuth();
  const router = useRouter();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loyaltyPoints, setLoyaltyPoints] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;

    const fetchData = async () => {
      try {
        const headers = { Authorization: `Bearer ${accessToken}` };

        // Fetch jobs
        const jobsRes = await fetch(`${API_URL}/portal/jobs`, { headers });
        const jobsData = jobsRes.ok ? await jobsRes.json() : [];

        // Fetch invoices
        const invoicesRes = await fetch(`${API_URL}/portal/invoices`, { headers });
        const invoicesData = invoicesRes.ok ? await invoicesRes.json() : [];

        // Fetch loyalty
        const loyaltyRes = await fetch(`${API_URL}/portal/loyalty`, { headers });
        const loyaltyData = loyaltyRes.ok ? await loyaltyRes.json() : { balance: 0 };

        setJobs(jobsData);
        setInvoices(invoicesData);
        setLoyaltyPoints(loyaltyData.balance);
      } catch (err) {
        console.error("Error fetching home dashboard data", err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [accessToken]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
      </div>
    );
  }

  // Derived Stats
  const unpaidInvoices = invoices.filter(inv => inv.status !== "paid");
  const totalBalanceDue = unpaidInvoices.reduce((acc, inv) => acc + inv.balance_cents, 0) / 100;
  const recentJobs = jobs.slice(0, 3);
  const recentInvoices = invoices.slice(0, 3);

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Welcome Banner */}
      <div className="p-8 rounded-2xl glass-card border border-white/5 relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="absolute top-0 right-0 w-80 h-80 bg-[var(--primary-color)]/5 rounded-full blur-3xl pointer-events-none" />
        <div className="space-y-2 relative z-10">
          <h1 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight">
            Hello, {customer?.first_name || "Valued Customer"}!
          </h1>
          <p className="text-slate-400 text-sm max-w-xl">
            Welcome to your customer portal. Here you can track your service requests, view and pay invoices, register equipment, and manage your membership benefits.
          </p>
        </div>
        <button
          onClick={() => router.push("/portal/request")}
          className="relative z-10 px-6 py-3 rounded-xl font-bold text-sm text-white hover:opacity-95 transition-all shadow-lg self-start md:self-auto cursor-pointer"
          style={{ backgroundColor: "var(--primary-color)" }}
        >
          Request Service
        </button>
      </div>

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Outstanding Balance */}
        <div className="p-6 rounded-2xl glass-card border border-white/5 flex items-center justify-between">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Balance Due</p>
            <h3 className="text-3xl font-extrabold text-white">${totalBalanceDue.toFixed(2)}</h3>
            <p className="text-xs text-slate-400">
              {unpaidInvoices.length} unpaid {unpaidInvoices.length === 1 ? "invoice" : "invoices"}
            </p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500">
            <FileText className="h-6 w-6" />
          </div>
        </div>

        {/* Completed Service Count */}
        <div className="p-6 rounded-2xl glass-card border border-white/5 flex items-center justify-between">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Service History</p>
            <h3 className="text-3xl font-extrabold text-white">{jobs.length}</h3>
            <p className="text-xs text-slate-400">Completed jobs</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-blue-500/10 flex items-center justify-center text-blue-500">
            <Wrench className="h-6 w-6" />
          </div>
        </div>

        {/* Loyalty Points */}
        <div className="p-6 rounded-2xl glass-card border border-white/5 flex items-center justify-between">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Loyalty Rewards</p>
            <h3 className="text-3xl font-extrabold text-white">{loyaltyPoints}</h3>
            <p className="text-xs text-slate-400">Available points balance</p>
          </div>
          <div className="h-12 w-12 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500">
            <Award className="h-6 w-6" />
          </div>
        </div>
      </div>

      {/* Main Grid: Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Recent Service History */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white">Recent Service History</h2>
            <button
              onClick={() => router.push("/portal/history")}
              className="text-xs font-semibold text-[var(--primary-color)] hover:underline flex items-center gap-1 cursor-pointer"
            >
              View All <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="space-y-3">
            {recentJobs.length === 0 ? (
              <div className="p-6 rounded-xl border border-white/5 text-center text-slate-500 text-sm">
                No recent service history found.
              </div>
            ) : (
              recentJobs.map(job => (
                <div 
                  key={job.id} 
                  className="p-5 rounded-xl glass-card border border-white/5 flex items-center justify-between hover:border-white/10 transition-all cursor-pointer"
                  onClick={() => router.push(`/portal/history`)}
                >
                  <div className="space-y-1 max-w-[70%]">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-400">{job.job_number}</span>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 capitalize">
                        {job.trade.replace("_", " ")}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold text-white truncate">{job.reported_problem}</h4>
                    {job.completed_at && (
                      <p className="text-xs text-slate-500 flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Completed: {new Date(job.completed_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 capitalize">
                    {job.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Recent Invoices */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white">Recent Invoices</h2>
            <button
              onClick={() => router.push("/portal/invoices")}
              className="text-xs font-semibold text-[var(--primary-color)] hover:underline flex items-center gap-1 cursor-pointer"
            >
              View All <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="space-y-3">
            {recentInvoices.length === 0 ? (
              <div className="p-6 rounded-xl border border-white/5 text-center text-slate-500 text-sm">
                No recent invoices found.
              </div>
            ) : (
              recentInvoices.map(inv => (
                <div 
                  key={inv.id} 
                  className="p-5 rounded-xl glass-card border border-white/5 flex items-center justify-between hover:border-white/10 transition-all cursor-pointer"
                  onClick={() => router.push(`/portal/invoices`)}
                >
                  <div className="space-y-1">
                    <span className="text-xs font-bold text-slate-400">Invoice #{inv.invoice_number}</span>
                    <h4 className="text-sm font-semibold text-white">
                      ${(inv.total_cents / 100).toFixed(2)}
                    </h4>
                    {inv.due_date && inv.status !== "paid" && (
                      <p className="text-xs text-amber-400 flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Due: {new Date(inv.due_date).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold px-2.5 py-1 rounded-lg ${
                      inv.status === "paid" 
                        ? "bg-emerald-500/10 text-emerald-400" 
                        : "bg-amber-500/10 text-amber-400"
                    } capitalize`}>
                      {inv.status}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
