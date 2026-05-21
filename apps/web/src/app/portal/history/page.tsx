"use client";

import React, { useState, useEffect } from "react";
import { 
  Search, 
  Filter, 
  Wrench, 
  Calendar, 
  ChevronRight, 
  X, 
  Loader2, 
  Image as ImageIcon 
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
  scheduled_start: string | null;
  scheduled_end: string | null;
  completed_at: string | null;
}

interface Photo {
  id: string;
  photo_type: string;
  cdn_url: string;
  caption: string | null;
  taken_at: string;
}

interface JobDetail extends Job {
  dispatcher_notes: string | null;
  arrived_at: string | null;
  photos: Photo[];
}

export default function PortalHistoryPage() {
  const { accessToken } = usePortalAuth();
  
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [tradeFilter, setTradeFilter] = useState("all");
  
  // Modal state
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Fetch jobs on mount
  useEffect(() => {
    if (!accessToken) return;

    const fetchJobs = async () => {
      try {
        const res = await fetch(`${API_URL}/portal/jobs`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const data = await res.json();
          setJobs(data);
        }
      } catch (err) {
        console.error("Failed to fetch jobs", err);
      } finally {
        setLoading(false);
      }
    };

    fetchJobs();
  }, [accessToken]);

  // Fetch job detail when modal opens
  useEffect(() => {
    if (!selectedJobId || !accessToken) {
      setJobDetail(null);
      return;
    }

    const fetchJobDetail = async () => {
      setLoadingDetail(true);
      try {
        const res = await fetch(`${API_URL}/portal/jobs/${selectedJobId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const data = await res.json();
          setJobDetail(data);
        }
      } catch (err) {
        console.error("Failed to fetch job detail", err);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchJobDetail();
  }, [selectedJobId, accessToken]);

  const filteredJobs = jobs.filter(job => {
    const matchesSearch = 
      job.job_number.toLowerCase().includes(search.toLowerCase()) ||
      job.reported_problem.toLowerCase().includes(search.toLowerCase());
    
    const matchesTrade = 
      tradeFilter === "all" || 
      job.trade.toLowerCase() === tradeFilter.toLowerCase();

    return matchesSearch && matchesTrade;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Service History</h1>
          <p className="text-slate-400 text-sm">Review your past repairs, service details, and notes.</p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row gap-4 p-4 rounded-xl glass-card border border-white/5">
        <div className="relative flex-grow">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by job number or problem description..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg glass-input text-slate-200 placeholder-slate-500 focus:outline-none text-sm"
          />
        </div>
        <div className="flex items-center gap-3">
          <Filter className="w-4 h-4 text-slate-400 hidden sm:block" />
          <select
            value={tradeFilter}
            onChange={(e) => setTradeFilter(e.target.value)}
            className="px-4 py-2.5 rounded-lg glass-input text-slate-300 focus:outline-none text-sm bg-gray-900 border border-white/5 cursor-pointer"
          >
            <option value="all">All Trades</option>
            <option value="hvac">HVAC</option>
            <option value="garage_door">Garage Door</option>
          </select>
        </div>
      </div>

      {/* Jobs List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="p-12 rounded-2xl glass-card border border-white/5 text-center text-slate-500">
          No services match your filters.
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredJobs.map(job => (
            <div 
              key={job.id} 
              onClick={() => setSelectedJobId(job.id)}
              className="p-5 rounded-xl glass-card border border-white/5 flex items-center justify-between hover:border-white/10 hover:bg-white/[0.01] transition-all cursor-pointer group"
            >
              <div className="flex items-start gap-4">
                <div className="h-10 w-10 rounded-lg bg-[var(--primary-color)]/10 flex items-center justify-center text-[var(--primary-color)] mt-1">
                  <Wrench className="h-5 w-5" />
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-400">{job.job_number}</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 capitalize">
                      {job.trade.replace("_", " ")}
                    </span>
                  </div>
                  <h3 className="text-base font-semibold text-white group-hover:text-[var(--primary-color)] transition-colors">
                    {job.reported_problem}
                  </h3>
                  {job.completed_at && (
                    <p className="text-xs text-slate-400 flex items-center gap-1.5">
                      <Calendar className="h-3.5 w-3.5 text-slate-500" />
                      Completed: {new Date(job.completed_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4">
                <span className="text-xs font-bold px-2.5 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 capitalize">
                  {job.status}
                </span>
                <ChevronRight className="h-5 w-5 text-slate-500 group-hover:text-white transition-colors" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail Modal */}
      {selectedJobId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-2xl bg-gray-900 border border-white/10 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  {loadingDetail ? "Loading details..." : jobDetail?.job_number}
                </h3>
                <p className="text-xs text-slate-400 capitalize">
                  {!loadingDetail && jobDetail && `${jobDetail.trade.replace("_", " ")} Service`}
                </p>
              </div>
              <button 
                onClick={() => setSelectedJobId(null)}
                className="p-1.5 rounded-lg border border-white/5 hover:border-white/20 text-slate-400 hover:text-white transition-all cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-6 flex-grow">
              {loadingDetail ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
                </div>
              ) : jobDetail ? (
                <>
                  {/* Summary Grid */}
                  <div className="grid grid-cols-2 gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5">
                    <div>
                      <p className="text-xs text-slate-500">Service Status</p>
                      <p className="text-sm font-bold text-emerald-400 capitalize">{jobDetail.status}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Job Type</p>
                      <p className="text-sm font-bold text-white capitalize">{jobDetail.job_type}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Scheduled Date</p>
                      <p className="text-sm font-semibold text-white">
                        {jobDetail.scheduled_start 
                          ? new Date(jobDetail.scheduled_start).toLocaleDateString() 
                          : "N/A"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Completed Date</p>
                      <p className="text-sm font-semibold text-white">
                        {jobDetail.completed_at 
                          ? new Date(jobDetail.completed_at).toLocaleDateString() 
                          : "N/A"}
                      </p>
                    </div>
                  </div>

                  {/* Problem Description */}
                  <div className="space-y-2">
                    <h4 className="text-sm font-semibold text-slate-350">Problem Reported</h4>
                    <p className="text-sm text-slate-200 bg-slate-800/40 p-4 rounded-xl border border-white/5 leading-relaxed">
                      {jobDetail.reported_problem}
                    </p>
                  </div>

                  {/* Service Notes */}
                  {jobDetail.dispatcher_notes && (
                    <div className="space-y-2">
                      <h4 className="text-sm font-semibold text-slate-350">Service Overview & Findings</h4>
                      <p className="text-sm text-slate-300 bg-slate-800/40 p-4 rounded-xl border border-white/5 leading-relaxed">
                        {jobDetail.dispatcher_notes}
                      </p>
                    </div>
                  )}

                  {/* Service Photos */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-semibold text-slate-350">Job Photo Documentation</h4>
                    {jobDetail.photos.length === 0 ? (
                      <p className="text-xs text-slate-500 italic">No photo records attached to this service.</p>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        {jobDetail.photos.map(photo => (
                          <div key={photo.id} className="rounded-xl border border-white/5 bg-slate-800/35 overflow-hidden">
                            <img 
                              src={photo.cdn_url} 
                              alt={photo.caption || photo.photo_type} 
                              className="w-full h-40 object-cover border-b border-white/5"
                            />
                            <div className="p-3">
                              <span className="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">
                                {photo.photo_type}
                              </span>
                              <p className="text-xs text-slate-300 mt-2 font-medium">
                                {photo.caption || "Service photo documentation"}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-center text-slate-500 text-sm">Failed to load details.</p>
              )}
            </div>
            
            <div className="p-4 border-t border-white/5 bg-gray-900/60 flex justify-end">
              <button 
                onClick={() => setSelectedJobId(null)}
                className="px-5 py-2 rounded-xl border border-white/5 hover:border-white/20 text-slate-300 hover:text-white font-semibold text-sm transition-all cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
