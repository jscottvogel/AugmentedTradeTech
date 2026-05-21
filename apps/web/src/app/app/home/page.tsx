"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useAuth } from "../../../hooks/useAuth";
import { AuthGuard } from "../../../components/AuthGuard";
import { 
  Home, 
  Briefcase, 
  Bot, 
  User, 
  Bell, 
  MapPin, 
  Clock, 
  ChevronRight, 
  Check, 
  Loader2, 
  Send, 
  LogOut, 
  Flame, 
  Wrench,
  Navigation,
  RefreshCw,
  AlertTriangle
} from "lucide-react";

export default function TechHomeScreen() {
  return (
    <AuthGuard>
      <HomeScreenContent />
    </AuthGuard>
  );
}

// Interfaces
interface Job {
  id: string;
  job_number: string;
  trade: string;
  job_type: string;
  priority: string;
  status: string;
  reported_problem: string;
  dispatcher_notes: string;
  scheduled_start: string;
  scheduled_end: string;
  customer: {
    id: string;
    first_name: string;
    last_name: string;
    address_line1: string;
    address_line2: string;
    city: string;
    state: string;
    zip: string;
  };
}

interface Stats {
  jobs_completed: number;
  earnings_today: number | null;
  earnings_enabled: boolean;
}

interface ChatMessage {
  sender: "user" | "ai";
  text: string;
  timestamp: Date;
}

function HomeScreenContent() {
  const { user, accessToken, logout, updateCurrentUser } = useAuth();
  
  // Navigation tab state: "home" | "pool" | "ai" | "profile"
  const [activeTab, setActiveTab] = useState<"home" | "pool" | "ai" | "profile">("home");
  
  // Home tab states
  const [scheduleType, setScheduleType] = useState<"today" | "upcoming">("today");
  const [todayJobs, setTodayJobs] = useState<Job[]>([]);
  const [upcomingJobs, setUpcomingJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<Stats>({ jobs_completed: 0, earnings_today: null, earnings_enabled: true });
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Pull to refresh states
  const [touchStart, setTouchStart] = useState<number | null>(null);
  const [pullProgress, setPullProgress] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Heartbeat & status duration states
  const [isAvailabilitySheetOpen, setIsAvailabilitySheetOpen] = useState(false);
  const [elapsedText, setElapsedText] = useState("");
  
  // Notification system
  const [notifications, setNotifications] = useState<{ id: string; text: string; time: string; read: boolean }[]>([
    { id: "1", text: "New emergency job assigned: J-802 at 2:00 PM", time: "10m ago", read: false },
    { id: "2", text: "Parts for Job J-711 have arrived at the warehouse", time: "2h ago", read: false },
  ]);
  const [showNotificationsDropdown, setShowNotificationsDropdown] = useState(false);

  // Mock Job Pool State
  const [poolJobs, setPoolJobs] = useState<Job[]>([
    {
      id: "pool_1",
      job_number: "J-POOL-01",
      trade: "hvac",
      job_type: "service",
      priority: "routine",
      status: "scheduled",
      reported_problem: "A/C unit blowing warm air. Fan is spinning but compressor doesn't turn on.",
      dispatcher_notes: "Customer available all afternoon.",
      scheduled_start: new Date(Date.now() + 4 * 3600 * 1000).toISOString(),
      scheduled_end: new Date(Date.now() + 6 * 3600 * 1000).toISOString(),
      customer: {
        id: "c_pool_1",
        first_name: "Robert",
        last_name: "Johnson",
        address_line1: "789 Pine Rd",
        address_line2: "",
        city: "Dallas",
        state: "TX",
        zip: "75204"
      }
    },
    {
      id: "pool_2",
      job_number: "J-POOL-02",
      trade: "garage_door",
      job_type: "maintenance",
      priority: "routine",
      status: "scheduled",
      reported_problem: "Tension springs squeaking loudly during operation.",
      dispatcher_notes: "Gate code is #4829",
      scheduled_start: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
      scheduled_end: new Date(Date.now() + 26 * 3600 * 1000).toISOString(),
      customer: {
        id: "c_pool_2",
        first_name: "Melissa",
        last_name: "White",
        address_line1: "101 Maple Ln",
        address_line2: "Apt 4B",
        city: "Dallas",
        state: "TX",
        zip: "75205"
      }
    }
  ]);
  const [claimingJobId, setClaimingJobId] = useState<string | null>(null);

  // AI Assistant Tab States
  const [aiChat, setAiChat] = useState<ChatMessage[]>([
    { sender: "ai", text: "Hello! I am your AI Diagnostics Assistant. How can I help you in the field today?", timestamp: new Date() }
  ]);
  const [chatInput, setChatInput] = useState("");
  const [isAiTyping, setIsAiTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Load schedule and stats
  const loadDashboardData = async () => {
    if (!accessToken) return;
    try {
      // Parallel fetches for jobs and stats
      const [resToday, resUpcoming, resStats] = await Promise.all([
        fetch(`${API_URL}/me/jobs/today`, { headers: { Authorization: `Bearer ${accessToken}` } }),
        fetch(`${API_URL}/me/jobs/upcoming`, { headers: { Authorization: `Bearer ${accessToken}` } }),
        fetch(`${API_URL}/me/stats/today`, { headers: { Authorization: `Bearer ${accessToken}` } }),
      ]);

      if (resToday.ok) {
        const dataToday = await resToday.json();
        setTodayJobs(dataToday);
      }
      if (resUpcoming.ok) {
        const dataUpcoming = await resUpcoming.json();
        setUpcomingJobs(dataUpcoming);
      }
      if (resStats.ok) {
        const dataStats = await resStats.json();
        setStats(dataStats);
      }
      setError(null);
    } catch (err) {
      console.error("Error loading dashboard data:", err);
      setError("Failed to sync schedule. Using offline fallback.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, [accessToken]);

  // Periodic heartbeat ping for active techs (every 5 minutes)
  useEffect(() => {
    if (!user || !user.is_active || user.role !== "tech" || !accessToken) return;

    const sendHeartbeat = () => {
      fetch(`${API_URL}/me/heartbeat`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      }).catch(err => console.error("Heartbeat error:", err));
    };

    sendHeartbeat();
    const interval = setInterval(sendHeartbeat, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [user?.is_active, accessToken]);

  // Status duration timer
  useEffect(() => {
    const statusChangedAt = user?.tech_profile?.status_changed_at;
    if (!statusChangedAt) {
      setElapsedText("");
      return;
    }

    const updateTimer = () => {
      const start = new Date(statusChangedAt).getTime();
      const diffMs = Date.now() - start;
      if (isNaN(start) || diffMs < 0) {
        setElapsedText("0m");
        return;
      }
      const diffSecs = Math.floor(diffMs / 1000);
      const mins = Math.floor(diffSecs / 60) % 60;
      const hours = Math.floor(diffSecs / 3600);
      
      if (hours > 0) {
        setElapsedText(`${hours}h ${mins}m`);
      } else {
        setElapsedText(`${mins}m`);
      }
    };

    updateTimer();
    const timerId = setInterval(updateTimer, 10000); // update every 10 seconds
    return () => clearInterval(timerId);
  }, [user?.tech_profile?.status_changed_at]);

  // Scroll chat window to bottom
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [aiChat, isAiTyping]);

  // Pull-to-refresh swipe listeners
  const handleTouchStart = (e: React.TouchEvent) => {
    if (window.scrollY === 0) {
      setTouchStart(e.touches[0].clientY);
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchStart === null) return;
    const currentY = e.touches[0].clientY;
    const diff = currentY - touchStart;
    if (diff > 0) {
      // Only pull down, restrict pull distance to 60px
      setPullProgress(Math.min(diff / 3, 60));
    }
  };

  const handleTouchEnd = () => {
    if (pullProgress >= 50) {
      setIsRefreshing(true);
      loadDashboardData().finally(() => {
        setIsRefreshing(false);
        setPullProgress(0);
      });
    } else {
      setPullProgress(0);
    }
    setTouchStart(null);
  };

  // Change Availability Status
  const handleStatusChange = async (newStatus: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_URL}/me/availability`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) {
        const data = await res.json();
        updateCurrentUser({ tech_profile: data.tech_profile });
        setIsAvailabilitySheetOpen(false);
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Claim job from pool
  const claimJob = async (job: Job) => {
    setClaimingJobId(job.id);
    setTimeout(() => {
      // Add mock job to today's schedule
      setTodayJobs((prev) => [...prev, { ...job, status: "confirmed" }]);
      // Remove from pool
      setPoolJobs((prev) => prev.filter((j) => j.id !== job.id));
      setClaimingJobId(null);
      // Notify user
      alert(`Job ${job.job_number} claimed successfully! Added to your schedule.`);
    }, 1200);
  };

  // AI Assistant Chat Submit
  const handleChatSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const userMsg: ChatMessage = { sender: "user", text: chatInput, timestamp: new Date() };
    setAiChat((prev) => [...prev, userMsg]);
    setChatInput("");
    setIsAiTyping(true);

    // Simulate AI response
    setTimeout(() => {
      let reply = "I'm analyzing the issue. Let me review our knowledge base for this unit.";
      const msgLower = chatInput.toLowerCase();
      if (msgLower.includes("error") || msgLower.includes("code")) {
        reply = "Error Code 3 flashes green. This indicates a pressure switch failed-open condition. Please check: 1) Obstructions in the vent piping. 2) Condensate drain line clog. 3) Correct pressure switch calibration.";
      } else if (msgLower.includes("wiring") || msgLower.includes("wire")) {
        reply = "Refer to terminal R for 24V power, Y for compressor control, G for indoor fan blower, and W for heating call. For heat pumps, check the O/B reversing valve terminal polarity.";
      } else if (msgLower.includes("hello") || msgLower.includes("hi")) {
        reply = "Hello! Tell me about the diagnostic code or system symptoms you are observing.";
      }

      setAiChat((prev) => [...prev, { sender: "ai", text: reply, timestamp: new Date() }]);
      setIsAiTyping(false);
    }, 1500);
  };

  // Quick prompt helper
  const handleQuickPrompt = (promptText: string) => {
    setChatInput(promptText);
  };

  // Maps Navigation URL helper
  const getNavUrl = (addr: Job["customer"]) => {
    const fullAddr = `${addr.address_line1} ${addr.address_line2 || ""}, ${addr.city}, ${addr.state} ${addr.zip}`;
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fullAddr)}`;
  };

  const activeStatus = user?.tech_profile?.availability_status || "offline";
  const unreadCount = notifications.filter(n => !n.read).length;

  return (
    <div
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      className="flex flex-col min-h-screen bg-slate-950 text-slate-100 font-sans max-w-[480px] mx-auto shadow-2xl relative pb-[80px]"
    >
      
      {/* PWA Pull to Refresh Display */}
      {pullProgress > 0 && (
        <div 
          style={{ height: `${pullProgress}px` }} 
          className="transition-[height] duration-75 flex items-center justify-center text-sky-400 text-xs overflow-hidden bg-slate-900 border-b border-sky-500/10"
        >
          {pullProgress >= 50 ? "Release to sync schedule..." : "Pull down to sync..."}
        </div>
      )}
      {isRefreshing && (
        <div className="h-[50px] flex items-center justify-center text-sky-400 text-xs bg-slate-900 border-b border-sky-500/10 gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Syncing with Augmented Trade Tech Cloud...
        </div>
      )}

      {/* Header Area */}
      <header className="flex items-center justify-between px-5 py-4 bg-slate-900 border-b border-slate-800/60 sticky top-0 z-50">
        {/* Branding */}
        <div className="flex items-center gap-2.5">
          <div className="bg-indigo-600 w-8 h-8 rounded-lg flex items-center justify-center text-white shadow-md shadow-indigo-600/20">
            <Wrench className="w-4 h-4" />
          </div>
          <span className="font-extrabold text-sm tracking-tight text-white uppercase">
            Augmented Trade Tech
          </span>
        </div>

        {/* Notifications & Avatar */}
        <div className="flex items-center gap-4 relative">
          {/* Notification bell */}
          <button 
            onClick={() => setShowNotificationsDropdown(!showNotificationsDropdown)}
            className="text-slate-400 hover:text-white cursor-pointer relative p-1.5 rounded-lg hover:bg-slate-800/50 transition-colors"
          >
            <Bell className="w-5 h-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 bg-red-500 text-white text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center">
                {unreadCount}
              </span>
            )}
          </button>

          {/* User profile avatar */}
          <button
            onClick={() => setActiveTab("profile")}
            className="cursor-pointer p-0 rounded-full focus:ring-2 focus:ring-indigo-500/50"
          >
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt="Profile"
                className="w-8 h-8 rounded-full object-cover border border-slate-700"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-slate-800 text-slate-100 flex items-center justify-center font-bold text-xs border border-slate-700">
                {user?.full_name?.charAt(0) || "T"}
              </div>
            )}
          </button>

          {/* Notifications Dropdown */}
          {showNotificationsDropdown && (
            <div className="absolute top-11 right-0 bg-slate-900 border border-slate-800 rounded-xl w-[280px] shadow-2xl p-2 z-[60] animate-in fade-in slide-in-from-top-2 duration-150">
              <div className="flex justify-between items-center p-2 border-b border-slate-800">
                <span className="font-bold text-xs">Notifications</span>
                <button 
                  onClick={() => {
                    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
                  }}
                  className="text-indigo-400 hover:text-indigo-300 text-[10px] font-semibold cursor-pointer"
                >
                  Mark all read
                </button>
              </div>
              <div className="max-h-[220px] overflow-y-auto mt-1">
                {notifications.map(n => (
                  <div 
                    key={n.id} 
                    className={`p-2.5 border-b border-slate-800/30 text-xs ${n.read ? "opacity-50" : "opacity-100"}`}
                  >
                    <p className="text-slate-300 leading-normal">{n.text}</p>
                    <span className="text-[10px] text-slate-500 mt-1 block">{n.time}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </header>

      {/* Persistent Availability Status Bar */}
      <div className="flex items-center justify-between px-5 py-2.5 bg-slate-900/40 border-b border-slate-900">
        <div className="flex items-center gap-2">
          {/* Status color indicator */}
          <div className={`w-2 h-2 rounded-full shadow-md ${
            activeStatus === "available" ? "bg-emerald-500 shadow-emerald-500/50" :
            activeStatus === "on_job" ? "bg-blue-500 shadow-blue-500/50" :
            activeStatus === "driving" ? "bg-purple-500 shadow-purple-500/50" :
            activeStatus === "break" ? "bg-amber-500 shadow-amber-500/50" :
            activeStatus === "off_duty" ? "bg-slate-500 shadow-slate-500/50" : "bg-red-500 shadow-red-500/50"
          }`} />
          <span className="font-bold text-xs capitalize text-slate-300">
            {activeStatus.replace("_", " ")}
          </span>
          {elapsedText && (
            <span className="text-[10px] text-slate-500">
              • {elapsedText}
            </span>
          )}
        </div>
        <button
          onClick={() => setIsAvailabilitySheetOpen(true)}
          className="bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 px-2.5 py-1 rounded-full text-[10px] font-bold cursor-pointer transition-colors"
        >
          Change
        </button>
      </div>

      {/* Main Content Area depending on active bottom tab */}
      <main className="p-4 flex-1 flex flex-col">
        
        {/* Error message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg text-xs mb-4 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* TAB 1: HOME DASHBOARD */}
        {activeTab === "home" && (
          <div className="flex-1 flex flex-col gap-4">
            {/* Quick Stats Banner */}
            <div className="grid grid-cols-2 gap-3">
              {/* Jobs Completed stats widget */}
              <div className="bg-slate-900/30 border border-slate-900 p-3.5 rounded-xl flex flex-col">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">COMPLETED TODAY</span>
                <span className="text-xl font-extrabold text-white mt-1">
                  {stats.jobs_completed}
                </span>
              </div>
              
              {/* Earnings today stats widget */}
              <div className="bg-slate-900/30 border border-slate-900 p-3.5 rounded-xl flex flex-col">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">TODAY'S EARNINGS</span>
                <span className="text-xl font-extrabold text-emerald-400 mt-1">
                  {stats.earnings_enabled && stats.earnings_today !== null 
                    ? `$${(stats.earnings_today / 100).toFixed(2)}`
                    : "—"
                  }
                </span>
                {!stats.earnings_enabled && (
                  <span className="text-[9px] text-slate-600 mt-0.5">Disabled by Admin</span>
                )}
              </div>
            </div>

            {/* Schedule type sliding toggler */}
            <div className="flex bg-slate-900 p-1 rounded-xl">
              <button
                onClick={() => setScheduleType("today")}
                className={`flex-1 py-2 rounded-lg border-none font-bold text-xs cursor-pointer transition-all duration-250 ${
                  scheduleType === "today" ? "bg-slate-800 text-white shadow-sm" : "bg-transparent text-slate-500 hover:text-slate-400"
                }`}
              >
                Today's Jobs ({todayJobs.length})
              </button>
              <button
                onClick={() => setScheduleType("upcoming")}
                className={`flex-1 py-2 rounded-lg border-none font-bold text-xs cursor-pointer transition-all duration-250 ${
                  scheduleType === "upcoming" ? "bg-slate-800 text-white shadow-sm" : "bg-transparent text-slate-500 hover:text-slate-400"
                }`}
              >
                Upcoming ({upcomingJobs.length})
              </button>
            </div>

            {/* Loading indicators */}
            {isLoading ? (
              <div className="flex flex-col gap-3">
                {[1, 2].map(i => (
                  <div key={i} className="h-40 rounded-xl bg-slate-900/40 border border-slate-900/60 animate-pulse" />
                ))}
              </div>
            ) : (
              <div className="flex-1 flex flex-col gap-3">
                {scheduleType === "today" ? (
                  todayJobs.length === 0 ? (
                    // Today's Empty State
                    <div className="bg-slate-900/10 border border-dashed border-slate-800/80 rounded-xl p-8 text-center my-auto flex flex-col items-center justify-center">
                      <Clock className="w-9 h-9 text-slate-600 mb-3" />
                      <h3 className="text-sm font-bold text-white mb-1">All caught up for today!</h3>
                      <p className="text-xs text-slate-500 max-w-xs mb-4">
                        There are no assigned work orders on your list for today.
                      </p>
                      <button
                        onClick={() => setScheduleType("upcoming")}
                        className="bg-slate-900 hover:bg-slate-800 border border-slate-850 hover:border-slate-750 text-indigo-400 px-4 py-2 rounded-lg text-xs font-semibold cursor-pointer transition"
                      >
                        Check Upcoming Jobs
                      </button>
                    </div>
                  ) : (
                    todayJobs.map(job => (
                      <JobCard key={job.id} job={job} getNavUrl={getNavUrl} />
                    ))
                  )
                ) : (
                  upcomingJobs.length === 0 ? (
                    <div className="bg-slate-900/10 border border-dashed border-slate-800/80 rounded-xl p-8 text-center my-auto flex flex-col items-center justify-center">
                      <Briefcase className="w-9 h-9 text-slate-600 mb-3" />
                      <h3 className="text-sm font-bold text-white mb-1">No upcoming jobs</h3>
                      <p className="text-xs text-slate-500">
                        You have no scheduled work orders for the next 7 days.
                      </p>
                    </div>
                  ) : (
                    upcomingJobs.map(job => (
                      <JobCard key={job.id} job={job} getNavUrl={getNavUrl} />
                    ))
                  )
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 2: JOB POOL TAB */}
        {activeTab === "pool" && (
          <div className="flex-1 flex flex-col gap-3">
            <div>
              <h2 className="font-extrabold text-sm text-white">Available Job Pool</h2>
              <p className="text-xs text-slate-500 mt-1">
                Claim unassigned jobs in your trades near your service area.
              </p>
            </div>

            {poolJobs.length === 0 ? (
              <div className="bg-slate-900/10 border border-dashed border-slate-800/80 rounded-xl p-8 text-center my-auto flex flex-col items-center justify-center">
                <Briefcase className="w-9 h-9 text-slate-600 mb-3" />
                <h3 className="text-sm font-bold text-white mb-1">Job Pool is Empty</h3>
                <p className="text-xs text-slate-500">
                  All unassigned work orders have been claimed. Check back later!
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {poolJobs.map((job) => (
                  <div key={job.id} className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 flex flex-col gap-3 shadow-md">
                    <div className="flex justify-between items-center">
                      <span className="text-xs font-bold text-indigo-400">{job.job_number}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        {job.customer.city}, {job.customer.state}
                      </span>
                    </div>

                    <div>
                      <p className="text-xs font-bold text-white uppercase">
                        {job.job_type} • {job.trade === "hvac" ? "HVAC" : "Garage Door"}
                      </p>
                      <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                        {job.reported_problem}
                      </p>
                    </div>

                    <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                      <Clock className="w-3.5 h-3.5" />
                      <span>
                        Est. Start: {new Date(job.scheduled_start).toLocaleDateString()} at {new Date(job.scheduled_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>

                    <button
                      onClick={() => claimJob(job)}
                      disabled={claimingJobId === job.id}
                      className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] text-white font-bold text-xs rounded-lg cursor-pointer transition shadow-lg shadow-indigo-650/20 flex items-center justify-center gap-1.5"
                    >
                      {claimingJobId === job.id ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          Claiming...
                        </>
                      ) : "Claim Work Order"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: AI DIAGNOSTICS TAB */}
        {activeTab === "ai" && (
          <div className="flex-1 flex flex-col h-[calc(100vh-210px)]">
            <div>
              <h2 className="font-extrabold text-sm text-white">AI Field Assistant</h2>
              <p className="text-xs text-slate-500 mt-1">
                Wisdom on-demand: Ask for error diagnostics, wiring references, or troubleshooting checklists.
              </p>
            </div>

            {/* Chat Messages */}
            <div className="flex-1 bg-slate-950 border border-slate-900 rounded-xl p-4 overflow-y-auto flex flex-col gap-3 my-3">
              {aiChat.map((msg, i) => (
                <div key={i} className={`max-w-[85%] p-3 rounded-xl text-xs leading-relaxed ${
                  msg.sender === "user" 
                    ? "self-end bg-indigo-600 text-white rounded-br-none" 
                    : "self-start bg-slate-900 text-slate-200 rounded-bl-none"
                }`}>
                  <p>{msg.text}</p>
                </div>
              ))}
              {isAiTyping && (
                <div className="self-start bg-slate-900 text-slate-400 p-3 rounded-xl rounded-bl-none text-xs flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                  Typing diagnostics...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* Quick Prompts Helper */}
            <div className="flex gap-2 overflow-x-auto pb-1 mb-2 scrollbar-none">
              {[
                { label: "Code 3 diagnostics", prompt: "Error Code 3 flashes green" },
                { label: "Reversing valve wire", prompt: "Wiring schematic for reversing valve" },
                { label: "Compressor checklist", prompt: "Checklist for compressor failure" },
              ].map((item, idx) => (
                <button 
                  key={idx}
                  onClick={() => handleQuickPrompt(item.prompt)}
                  className="bg-slate-900 border border-slate-850 hover:border-slate-750 text-slate-300 px-3 py-1.5 rounded-full text-[10px] font-medium whitespace-nowrap cursor-pointer transition-colors"
                >
                  {item.label}
                </button>
              ))}
            </div>

            {/* Chat Input form */}
            <form onSubmit={handleChatSubmit} className="flex gap-2">
              <input
                type="text"
                placeholder="Ask AI diagnostic question..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
              />
              <button
                type="submit"
                className="bg-indigo-600 hover:bg-indigo-500 text-white p-2.5 rounded-xl cursor-pointer transition flex items-center justify-center shadow-lg shadow-indigo-650/20"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}

        {/* TAB 4: PROFILE & LOGOUT */}
        {activeTab === "profile" && (
          <div className="flex-1 flex flex-col gap-4">
            {/* Tech Profile Summary */}
            <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-6 text-center">
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt="Avatar"
                  className="w-20 h-20 rounded-full object-cover mx-auto mb-3 border-2 border-indigo-500/80 shadow-md"
                />
              ) : (
                <div className="w-20 h-20 rounded-full bg-slate-800 text-white font-extrabold text-2xl flex items-center justify-center mx-auto mb-3 border-2 border-slate-700">
                  {user?.full_name?.charAt(0) || "T"}
                </div>
              )}

              <h3 className="font-bold text-white text-base">{user?.full_name}</h3>
              <p className="text-xs text-slate-500 mt-1">{user?.email}</p>
              <span className="inline-block px-2.5 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-550/20 text-indigo-400 text-[9px] font-bold uppercase mt-3">
                {user?.role} member
              </span>
            </div>

            {/* Profile trades / skills */}
            <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 flex flex-col gap-3">
              <h4 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">TRADES & CORE SKILLS</h4>
              <div className="flex flex-wrap gap-2">
                {user?.tech_profile?.trades?.map((t, idx) => (
                  <span key={idx} className="bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs px-2.5 py-1 rounded-lg font-medium">
                    {t}
                  </span>
                ))}
                {user?.tech_profile?.skills?.map((s, idx) => (
                  <span key={idx} className="bg-slate-850/40 border border-slate-800 text-slate-300 text-xs px-2.5 py-1 rounded-lg">
                    {s}
                  </span>
                ))}
              </div>
            </div>

            {/* Logout button */}
            <button
              onClick={logout}
              className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 py-3 rounded-xl font-bold text-xs cursor-pointer transition text-center flex items-center justify-center gap-1.5"
            >
              <LogOut className="w-4 h-4" />
              Sign Out of Device
            </button>
          </div>
        )}
      </main>

      {/* Bottom Navigation Bar */}
      <nav className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-[480px] h-16 bg-slate-900/90 backdrop-blur-md border-t border-slate-800/80 flex items-center justify-around z-50">
        {[
          { key: "home", label: "Home", icon: <Home className="w-5 h-5" /> },
          { key: "pool", label: "Job Pool", icon: <Briefcase className="w-5 h-5" /> },
          { key: "ai", label: "AI", icon: <Bot className="w-5 h-5" /> },
          { key: "profile", label: "Profile", icon: <User className="w-5 h-5" /> }
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key as any)}
            className={`flex flex-col items-center gap-1 cursor-pointer transition-colors px-3 py-1.5 rounded-lg border-none bg-transparent ${
              activeTab === tab.key ? "text-indigo-400 font-bold" : "text-slate-500 hover:text-slate-400 font-medium"
            }`}
          >
            {tab.icon}
            <span className="text-[10px]">{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* Availability Status switcher Overlay/Bottom-Sheet */}
      {isAvailabilitySheetOpen && (
        <div className="fixed inset-0 bg-black/65 z-[100] flex items-end justify-center">
          <div 
            onClick={() => setIsAvailabilitySheetOpen(false)}
            className="absolute inset-0 cursor-default"
          />

          {/* Bottom sheet dialog container */}
          <div className="relative bg-slate-950 border-t border-slate-800 rounded-t-2xl w-full max-w-[480px] p-5 flex flex-col gap-4 shadow-2xl z-10 animate-[slideUp_0.25s_cubic-bezier(0.16,1,0.3,1)_forwards]">
            <div className="flex justify-between items-center border-b border-slate-900 pb-3">
              <span className="font-extrabold text-sm text-white">Update Availability Status</span>
              <button 
                onClick={() => setIsAvailabilitySheetOpen(false)}
                className="text-slate-500 hover:text-slate-400 text-xs font-semibold cursor-pointer border-none bg-transparent"
              >
                Close
              </button>
            </div>

            {/* List of status options */}
            <div className="flex flex-col gap-2">
              {[
                { status: "available", label: "Available", desc: "Ready for automatic or manual dispatch", color: "bg-emerald-500" },
                { status: "on_job", label: "On Job", desc: "Currently performing repair/maintenance", color: "bg-blue-500" },
                { status: "driving", label: "Driving", desc: "En route to a client address", color: "bg-purple-500" },
                { status: "break", label: "Break", desc: "Lunch or short rest period", color: "bg-amber-500" },
                { status: "off_duty", label: "Off Duty", desc: "Completed shift for the day", color: "bg-slate-500" },
                { status: "offline", label: "Offline", desc: "App closed / no active signals", color: "bg-red-500" }
              ].map((opt) => (
                <button
                  key={opt.status}
                  onClick={() => handleStatusChange(opt.status)}
                  className={`flex items-center justify-between p-3 rounded-xl border text-left cursor-pointer transition-all ${
                    activeStatus === opt.status 
                      ? "bg-indigo-500/10 border-indigo-500" 
                      : "bg-slate-900/30 border-slate-900/80 hover:border-slate-850"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${opt.color}`} />
                    <div>
                      <p className="font-bold text-xs text-white leading-normal">{opt.label}</p>
                      <p className="text-[10px] text-slate-500 mt-0.5 leading-normal">{opt.desc}</p>
                    </div>
                  </div>
                  {activeStatus === opt.status && (
                    <Check className="w-4 h-4 text-indigo-400" />
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

// Sub-Component: Job Card
function JobCard({ job, getNavUrl }: { job: Job; getNavUrl: (addr: Job["customer"]) => string }) {
  const isEmergency = job.priority === "emergency";
  const isUrgent = job.priority === "urgent";
  const isHVAC = job.trade === "hvac";

  const startTime = new Date(job.scheduled_start);
  const endTime = new Date(job.scheduled_end);
  const timeStr = isNaN(startTime.getTime())
    ? "Scheduled Time"
    : `${startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${endTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;

  return (
    <div className="bg-slate-900/30 border border-slate-900 rounded-xl p-4 flex flex-col gap-3 shadow-md relative overflow-hidden">
      
      <Link href={`/app/jobs/${job.id}`} className="flex flex-col gap-3 no-underline text-inherit hover:opacity-85 transition duration-150">
        {/* Card Header: Trade and Priority badges */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            {isHVAC ? (
              <div className="flex items-center gap-1.5 bg-sky-500/10 px-2 py-0.5 rounded text-sky-400 text-[10px] font-bold uppercase border border-sky-500/10">
                <Flame className="w-3 h-3 rotate-180" />
                <span>HVAC</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 bg-purple-500/10 px-2 py-0.5 rounded text-purple-400 text-[10px] font-bold uppercase border border-purple-500/10">
                <Wrench className="w-3 h-3" />
                <span>Garage</span>
              </div>
            )}
          </div>

          {/* Priority Badge */}
          <span className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase border ${
            isEmergency ? "bg-red-500/10 border-red-500/20 text-red-400" :
            isUrgent ? "bg-amber-500/10 border-amber-500/20 text-amber-400" :
            "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
          }`}>
            {job.priority}
          </span>
        </div>

        {/* Scheduled Time Window */}
        <div className="flex items-center gap-1.5 text-slate-400 text-xs">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          <span className="font-semibold">{timeStr}</span>
        </div>

        {/* Customer Name and address */}
        <div>
          <h4 className="text-xs font-bold text-white">
            {job.customer.first_name} {job.customer.last_name}
          </h4>
          <p className="text-[11px] text-slate-400 mt-1 leading-normal">
            {job.customer.address_line1} {job.customer.address_line2 ? `, ${job.customer.address_line2}` : ""}
            <br />
            {job.customer.city}, {job.customer.state} {job.customer.zip}
          </p>
        </div>

        {/* Reported Problem */}
        {job.reported_problem && (
          <div className="bg-slate-950/40 border border-slate-900 p-2.5 rounded-lg text-[10px] text-slate-300 leading-normal">
            <span className="font-bold text-slate-500 block mb-0.5">Problem Reported:</span> 
            {job.reported_problem}
          </div>
        )}
      </Link>

      {/* Action panel */}
      <div className="flex gap-2 items-center mt-1">
        {/* Status chip */}
        <span className={`text-[10px] px-2.5 py-1.5 rounded-lg font-bold border capitalize ${
          job.status === "completed" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-450" :
          job.status === "in_progress" ? "bg-blue-500/10 border-blue-500/20 text-blue-400" :
          job.status === "en_route" ? "bg-purple-500/10 border-purple-500/20 text-purple-400" :
          "bg-slate-800/30 border-slate-800 text-slate-400"
        }`}>
          {job.status.replace("_", " ")}
        </span>

        {/* Details Button */}
        <Link
          href={`/app/jobs/${job.id}`}
          className="flex-1 bg-indigo-650 hover:bg-indigo-600 text-white py-1.5 rounded-lg text-[10px] font-bold text-center flex items-center justify-center gap-1 shadow-md shadow-indigo-650/15 cursor-pointer transition no-underline"
        >
          View Job Card
        </Link>

        {/* Navigation Action */}
        <a
          href={getNavUrl(job.customer)}
          target="_blank"
          rel="noopener noreferrer"
          className="bg-slate-900 hover:bg-slate-850 border border-slate-800 text-indigo-400 p-2 rounded-lg text-[10px] font-bold text-center flex items-center justify-center gap-1 transition no-underline cursor-pointer"
          title="Navigate to Site"
        >
          <Navigation className="w-3.5 h-3.5 fill-current" />
        </a>
      </div>

    </div>
  );
}
