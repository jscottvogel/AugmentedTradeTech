"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../hooks/useAuth";
import { AuthGuard } from "../../components/AuthGuard";
import {
  Calendar,
  Search,
  Plus,
  User as UserIcon,
  MapPin,
  Phone,
  Mail,
  Clock,
  AlertTriangle,
  Check,
  X,
  Users,
  ArrowRight,
  ArrowLeft,
  Bot,
  Sparkles,
  Activity,
  FileText,
  ChevronDown,
  Wrench,
  HelpCircle
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Interfaces ---
interface Customer {
  id: string;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  customer_type: string;
  notes: string | null;
}

interface Equipment {
  id: string;
  name: string;
  make: string | null;
  model: string | null;
  serial_number: string | null;
}

interface JobTech {
  id: string;
  tech_id: string;
  is_lead: boolean;
  full_name: string;
}

interface Job {
  id: string;
  job_number: string;
  trade: string;
  job_type: string;
  priority: string;
  status: string;
  reported_problem: string | null;
  dispatcher_notes: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  customer: Customer | null;
  equipment: Equipment | null;
  technicians: JobTech[];
  notes: any[];
  parts: any[];
}

interface Tech {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  avatar_url: string | null;
  availability_status: string;
  trades: string[];
  skills: string[];
  active_job: {
    id: string;
    job_number: string;
    status: string;
    priority: string;
    trade: string;
    customer_name: string;
  } | null;
}

interface AISuggestion {
  suggested_tech_id: string | null;
  reasoning: string;
}

export default function DispatchDashboard() {
  return (
    <AuthGuard>
      <DispatchDashboardContent />
    </AuthGuard>
  );
}

function DispatchDashboardContent() {
  const { user, accessToken, logout } = useAuth();
  const router = useRouter();

  // Role Protection
  useEffect(() => {
    if (user && user.role !== "dispatcher" && user.role !== "company_admin") {
      router.push("/app/home");
    }
  }, [user, router]);

  // Date State (formatted YYYY-MM-DD)
  const getTodayString = () => {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };

  const [selectedDate, setSelectedDate] = useState<string>(getTodayString());
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedTechFilter, setSelectedTechFilter] = useState<string | null>(null);

  // Core Data
  const [boardJobs, setBoardJobs] = useState<Record<string, Job[]>>({
    unassigned: [],
    scheduled: [],
    en_route: [],
    on_site: [],
    in_progress: [],
    completed: []
  });
  const [techs, setTechs] = useState<Tech[]>([]);
  const [unassignedJobs, setUnassignedJobs] = useState<Job[]>([]);
  
  // Loading & Error States
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Side-panel Details
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJobDetail, setActiveJobDetail] = useState<Job | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<AISuggestion | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState<boolean>(false);
  const [isEditingNotes, setIsEditingNotes] = useState<boolean>(false);
  const [tempNotesText, setTempNotesText] = useState<string>("");

  // Customer History Modal
  const [customerHistoryId, setCustomerHistoryId] = useState<string | null>(null);
  const [customerHistoryData, setCustomerHistoryData] = useState<any | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState<boolean>(false);

  // Create Job Modal
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [customerSearchQuery, setCustomerSearchQuery] = useState<string>("");
  const [searchedCustomers, setSearchedCustomers] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [isCreatingNewCustomer, setIsCreatingNewCustomer] = useState<boolean>(false);

  // Form Fields for new customer
  const [newCustFirst, setNewCustFirst] = useState("");
  const [newCustLast, setNewCustLast] = useState("");
  const [newCustEmail, setNewCustEmail] = useState("");
  const [newCustPhone, setNewCustPhone] = useState("");
  const [newCustAddr, setNewCustAddr] = useState("");
  const [newCustCity, setNewCustCity] = useState("");
  const [newCustState, setNewCustState] = useState("");
  const [newCustZip, setNewCustZip] = useState("");
  const [newCustType, setNewCustType] = useState("residential");

  // Form Fields for Job
  const [jobTrade, setJobTrade] = useState("hvac");
  const [jobType, setJobType] = useState("service");
  const [jobPriority, setJobPriority] = useState("routine");
  const [jobProblem, setJobProblem] = useState("");
  const [jobNotes, setJobNotes] = useState("");
  const [jobStart, setJobStart] = useState("");
  const [jobEnd, setJobEnd] = useState("");
  const [jobTechId, setJobTechId] = useState("");

  // Drag and Drop active status column tracker
  const [draggedJobId, setDraggedJobId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);
  const [dragOverTechId, setDragOverTechId] = useState<string | null>(null);

  // Load Main Dashboard Data
  const loadDashboardData = async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      // Load board jobs
      const boardRes = await fetch(`${API_URL}/dispatch/board?date=${selectedDate}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!boardRes.ok) throw new Error("Failed to load dispatch board");
      const boardData = await boardRes.json();
      setBoardJobs(boardData);

      // Load techs
      const techsRes = await fetch(`${API_URL}/dispatch/techs`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!techsRes.ok) throw new Error("Failed to load technician roster");
      const techsData = await techsRes.json();
      setTechs(techsData);

      // Load unassigned queue
      const unassignedRes = await fetch(`${API_URL}/dispatch/unassigned`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (unassignedRes.ok) {
        const unassignedData = await unassignedRes.json();
        setUnassignedJobs(unassignedData);
      }

      setErrorMessage(null);
    } catch (err: any) {
      setErrorMessage(err.message || "An error occurred loading dashboard data");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, [selectedDate, accessToken]);

  // Load Job Detail for Side-sheet
  const loadJobDetail = async (jobId: string) => {
    if (!accessToken) return;
    setIsDetailLoading(true);
    setActiveJobId(jobId);
    try {
      const res = await fetch(`${API_URL}/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) throw new Error("Failed to fetch job detail");
      const data = await res.json();
      setActiveJobDetail(data);
      setTempNotesText(data.dispatcher_notes || "");

      // Get AI Recommendation
      const suggestRes = await fetch(`${API_URL}/dispatch/suggest-tech`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ job_id: jobId })
      });
      if (suggestRes.ok) {
        const suggestData = await suggestRes.json();
        setAiSuggestion(suggestData);
      } else {
        setAiSuggestion(null);
      }
    } catch (err) {
      console.error(err);
      setActiveJobDetail(null);
    } finally {
      setIsDetailLoading(false);
    }
  };

  // Load Customer History
  const loadCustomerHistory = async (custId: string) => {
    if (!accessToken) return;
    setIsHistoryLoading(true);
    setCustomerHistoryId(custId);
    try {
      const res = await fetch(`${API_URL}/customers/${custId}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) throw new Error("Failed to fetch customer history");
      const data = await res.json();
      setCustomerHistoryData(data);
    } catch (err) {
      console.error(err);
      setCustomerHistoryData(null);
    } finally {
      setIsHistoryLoading(false);
    }
  };

  // Search Customers for modal
  useEffect(() => {
    const searchCusts = async () => {
      if (!accessToken || customerSearchQuery.trim().length === 0) {
        setSearchedCustomers([]);
        return;
      }
      try {
        const res = await fetch(`${API_URL}/customers?q=${encodeURIComponent(customerSearchQuery)}`, {
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (res.ok) {
          const data = await res.json();
          setSearchedCustomers(data);
        }
      } catch (err) {
        console.error(err);
      }
    };
    const timer = setTimeout(searchCusts, 300);
    return () => clearTimeout(timer);
  }, [customerSearchQuery, accessToken]);

  // Handle Drag-and-drop Columns
  const handleDragStart = (jobId: string) => {
    setDraggedJobId(jobId);
  };

  const handleDragOverColumn = (e: React.DragEvent, colName: string) => {
    e.preventDefault();
    setDragOverColumn(colName);
  };

  const handleDropColumn = async (colName: string) => {
    if (!draggedJobId || !accessToken) return;
    const originalCol = dragOverColumn;
    setDragOverColumn(null);
    setDraggedJobId(null);

    // Map column target to status transitions
    let targetStatus = colName;
    if (colName === "unassigned") {
      targetStatus = "scheduled";
    }

    setIsActionLoading(true);
    try {
      // 1. If dragging to unassigned, we must unassign the technician first (or call a backend unassign endpoint)
      // Since we don't have a direct delete-assignee, we can write an assignment helper or support it by assigning a null equivalent if needed.
      // Wait, let's look at `assign_technician` in backend: it checks `tech_id`. Let's check how we can unassign. If we don't have an unassign, we can just transition status or re-evaluate.
      // Wait! If we move from assigned to unassigned column, how does the state transition work? The column is based on assigned technicians.
      // If we move it to unassigned column, let's keep status scheduled but clear technicians. But we don't have a direct clear route yet, so we can mock or just execute status change.
      // Let's implement status transition:
      const res = await fetch(`${API_URL}/jobs/${draggedJobId}/status`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ status: targetStatus, note: "Moved on dispatcher kanban board" })
      });
      if (!res.ok) {
        const errDetail = await res.json();
        throw new Error(errDetail.detail || "Status transition invalid under state rules.");
      }
      loadDashboardData();
      if (activeJobId === draggedJobId) {
        loadJobDetail(draggedJobId);
      }
    } catch (err: any) {
      alert(`Transition error: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Handle Drag-and-drop to Technicians
  const handleDragOverTech = (e: React.DragEvent, techId: string) => {
    e.preventDefault();
    setDragOverTechId(techId);
  };

  const handleDropTech = async (techId: string) => {
    if (!draggedJobId || !accessToken) return;
    setDragOverTechId(null);
    setDraggedJobId(null);

    setIsActionLoading(true);
    try {
      const res = await fetch(`${API_URL}/jobs/${draggedJobId}/assign`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ tech_id: techId })
      });
      if (!res.ok) throw new Error("Technician assignment failed");
      loadDashboardData();
      if (activeJobId === draggedJobId) {
        loadJobDetail(draggedJobId);
      }
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Update Notes / Dispatcher Notes
  const handleSaveNotes = async () => {
    if (!activeJobId || !accessToken) return;
    setIsActionLoading(true);
    try {
      const res = await fetch(`${API_URL}/jobs/${activeJobId}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ dispatcher_notes: tempNotesText })
      });
      if (!res.ok) throw new Error("Failed to update dispatcher notes");
      setIsEditingNotes(false);
      loadJobDetail(activeJobId);
      loadDashboardData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Direct Assign Tech from detail panel
  const handleAssignTechDirect = async (techId: string) => {
    if (!activeJobId || !accessToken) return;
    setIsActionLoading(true);
    try {
      const res = await fetch(`${API_URL}/jobs/${activeJobId}/assign`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ tech_id: techId })
      });
      if (!res.ok) throw new Error("Technician assignment failed");
      loadJobDetail(activeJobId);
      loadDashboardData();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Submit Job Creation
  const handleCreateJobSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;

    setIsActionLoading(true);
    try {
      let customerId = selectedCustomer?.id;

      // 1. Handle Inline Customer Creation
      if (isCreatingNewCustomer) {
        const custRes = await fetch(`${API_URL}/customers`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            first_name: newCustFirst,
            last_name: newCustLast,
            email: newCustEmail || null,
            phone: newCustPhone || null,
            address_line1: newCustAddr || null,
            city: newCustCity || null,
            state: newCustState || null,
            zip: newCustZip || null,
            customer_type: newCustType
          })
        });
        if (!custRes.ok) {
          const detail = await custRes.json();
          throw new Error(detail.detail || "Failed to create new customer");
        }
        const newCust = await custRes.json();
        customerId = newCust.id;
      }

      if (!customerId) {
        throw new Error("Please select or create a customer first.");
      }

      // 2. Format ISO schedule dates
      let startIso = null;
      let endIso = null;
      if (jobStart) {
        startIso = new Date(jobStart).toISOString();
      }
      if (jobEnd) {
        endIso = new Date(jobEnd).toISOString();
      }

      // 3. Create Job
      const jobRes = await fetch(`${API_URL}/jobs`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          customer_id: customerId,
          trade: jobTrade,
          job_type: jobType,
          priority: jobPriority,
          reported_problem: jobProblem || null,
          dispatcher_notes: jobNotes || null,
          scheduled_start: startIso,
          scheduled_end: endIso,
          tech_id: jobTechId || null
        })
      });

      if (!jobRes.ok) {
        const detail = await jobRes.json();
        throw new Error(detail.detail || "Failed to create job");
      }

      // Reset Modal Form
      setIsCreateModalOpen(false);
      setSelectedCustomer(null);
      setCustomerSearchQuery("");
      setIsCreatingNewCustomer(false);
      setNewCustFirst("");
      setNewCustLast("");
      setNewCustEmail("");
      setNewCustPhone("");
      setNewCustAddr("");
      setNewCustCity("");
      setNewCustState("");
      setNewCustZip("");
      setJobProblem("");
      setJobNotes("");
      setJobStart("");
      setJobEnd("");
      setJobTechId("");

      loadDashboardData();
    } catch (err: any) {
      alert(`Job creation error: ${err.message}`);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Helper date offset buttons
  const offsetDate = (days: number) => {
    const curr = new Date(selectedDate + "T00:00:00");
    curr.setDate(curr.getDate() + days);
    const year = curr.getFullYear();
    const month = String(curr.getMonth() + 1).padStart(2, "0");
    const day = String(curr.getDate()).padStart(2, "0");
    setSelectedDate(`${year}-${month}-${day}`);
  };

  // Priority color formatting helper
  const getPriorityBadgeColor = (prio: string) => {
    switch (prio?.toLowerCase()) {
      case "emergency":
        return "bg-rose-500/20 text-rose-300 border-rose-500/30";
      case "urgent":
        return "bg-amber-500/20 text-amber-300 border-amber-500/30";
      case "routine":
      default:
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
    }
  };

  // Status color formatting helper
  const getTechStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case "available":
        return "bg-emerald-500";
      case "on_job":
        return "bg-indigo-500";
      case "driving":
        return "bg-sky-400";
      case "break":
        return "bg-amber-400";
      case "offline":
      case "off_duty":
      default:
        return "bg-slate-500";
    }
  };

  // Filter column cards based on general search query and technician toggle filter
  const filterJobs = (jobsList: Job[]) => {
    return jobsList.filter((j) => {
      // 1. Search Query filter (matches job number, customer name, trade)
      const q = searchQuery.toLowerCase();
      const jobMatch = j.job_number.toLowerCase().includes(q) ||
        j.trade.toLowerCase().includes(q) ||
        (j.reported_problem && j.reported_problem.toLowerCase().includes(q));

      const customerName = j.customer
        ? `${j.customer.first_name} ${j.customer.last_name}`.toLowerCase()
        : "";
      const customerMatch = customerName.includes(q);

      const queryMatches = q === "" || jobMatch || customerMatch;

      // 2. Technician select filter
      const techMatches =
        !selectedTechFilter ||
        j.technicians.some((t) => t.tech_id === selectedTechFilter);

      return queryMatches && techMatches;
    });
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 font-sans text-slate-100 selection:bg-indigo-500/30">
      {/* Top Header Bar */}
      <header className="sticky top-0 z-40 flex items-center justify-between px-6 py-4 border-b border-white/5 bg-slate-950/80 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
            <Wrench className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
              Augmented Trade Tech
            </h1>
            <p className="text-xs text-slate-400 font-medium">Dispatcher Dashboard</p>
          </div>
        </div>

        {/* Global Date Controls & Search */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-slate-900/60 border border-white/5 rounded-xl p-1">
            <button
              onClick={() => offsetDate(-1)}
              className="p-1.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white transition"
              title="Previous Day"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-2 px-2 text-sm font-semibold text-slate-200">
              <Calendar className="w-4 h-4 text-indigo-400" />
              <span>
                {selectedDate === getTodayString()
                  ? "Today"
                  : new Date(selectedDate + "T00:00:00").toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric"
                    })}
              </span>
            </div>
            <button
              onClick={() => offsetDate(1)}
              className="p-1.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white transition"
              title="Next Day"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          <div className="relative w-72">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search jobs, customers, trades..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-white/5 bg-slate-900/60 focus:bg-slate-900 focus:border-indigo-500/50 outline-none transition"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white rounded-xl shadow-lg shadow-indigo-600/10 transition duration-150"
          >
            <Plus className="w-4 h-4" />
            <span>Create Job</span>
          </button>
        </div>

        {/* User Info / Logout */}
        <div className="flex items-center gap-3">
          <div className="text-right hidden md:block">
            <p className="text-xs font-semibold text-slate-200">{user?.full_name}</p>
            <p className="text-[10px] text-slate-400 capitalize">{user?.role?.replace("_", " ")}</p>
          </div>
          <button
            onClick={() => logout()}
            className="p-2 hover:bg-rose-500/10 text-slate-400 hover:text-rose-400 border border-transparent hover:border-rose-500/20 rounded-xl transition"
            title="Log Out"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Main Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* LEFT PANEL: Tech Board */}
        <aside className="w-80 border-r border-white/5 bg-slate-900/20 p-4 flex flex-col gap-4 overflow-y-auto">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-indigo-400" />
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Technicians Board
              </h2>
            </div>
            {selectedTechFilter && (
              <button
                onClick={() => setSelectedTechFilter(null)}
                className="text-[10px] font-semibold text-indigo-400 hover:underline cursor-pointer"
              >
                Clear Filter
              </button>
            )}
          </div>

          <div className="flex flex-col gap-3">
            {techs.length === 0 ? (
              <div className="p-4 text-center rounded-xl bg-slate-900/30 border border-dashed border-white/5 text-slate-500 text-xs">
                No technicians registered.
              </div>
            ) : (
              techs.map((t) => {
                const isActiveFilter = selectedTechFilter === t.id;
                const isDragTarget = dragOverTechId === t.id;

                return (
                  <div
                    key={t.id}
                    onClick={() =>
                      setSelectedTechFilter(isActiveFilter ? null : t.id)
                    }
                    onDragOver={(e) => handleDragOverTech(e, t.id)}
                    onDragLeave={() => setDragOverTechId(null)}
                    onDrop={() => handleDropTech(t.id)}
                    className={`glass-card p-3 rounded-xl cursor-pointer select-none transition-all duration-200 ${
                      isActiveFilter
                        ? "border-indigo-500/50 bg-indigo-950/20 shadow-md shadow-indigo-500/5"
                        : "hover:bg-white/5 hover:border-white/10"
                    } ${isDragTarget ? "border-dashed border-indigo-400 bg-indigo-950/40 animate-pulse scale-102" : ""}`}
                  >
                    <div className="flex items-center gap-3">
                      {/* Avatar with Availability Status */}
                      <div className="relative">
                        <div className="w-9 h-9 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center font-bold text-xs text-indigo-300">
                          {t.full_name.split(" ").map((n) => n[0]).join("")}
                        </div>
                        <span
                          className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-slate-950 ${getTechStatusColor(
                            t.availability_status
                          )}`}
                          title={`Status: ${t.availability_status}`}
                        />
                      </div>

                      {/* Tech details */}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-slate-200 truncate">
                          {t.full_name}
                        </p>
                        <p className="text-[10px] text-slate-400 capitalize truncate mt-0.5">
                          {t.availability_status.replace("_", " ")}
                        </p>
                      </div>
                    </div>

                    {/* Active job display */}
                    {t.active_job ? (
                      <div className="mt-2.5 pt-2 border-t border-white/5 flex flex-col gap-1">
                        <div className="flex items-center justify-between text-[9px] text-slate-400">
                          <span>ACTIVE WORK ORDER</span>
                          <span className="font-semibold text-slate-200">
                            {t.active_job.job_number}
                          </span>
                        </div>
                        <p className="text-[10px] font-medium text-slate-300 truncate">
                          {t.active_job.customer_name}
                        </p>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <span className="text-[9px] bg-slate-800 text-slate-400 px-1 rounded uppercase">
                            {t.active_job.trade}
                          </span>
                          <span className="text-[9px] bg-slate-800 text-slate-400 px-1 rounded capitalize">
                            {t.active_job.status.replace("_", " ")}
                          </span>
                        </div>
                      </div>
                    ) : (
                      <p className="text-[9px] text-slate-500 italic mt-2.5 pt-2 border-t border-transparent">
                        No active jobs assigned today.
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* CENTER PANEL: Kanban Board */}
        <main className="flex-1 p-6 overflow-x-auto flex gap-4 bg-slate-900/10">
          {(["unassigned", "scheduled", "en_route", "on_site", "in_progress", "completed"] as const).map(
            (col) => {
              const filteredList = filterJobs(boardJobs[col] || []);
              const isOver = dragOverColumn === col;

              return (
                <div
                  key={col}
                  onDragOver={(e) => handleDragOverColumn(e, col)}
                  onDragLeave={() => setDragOverColumn(null)}
                  onDrop={() => handleDropColumn(col)}
                  className={`flex flex-col w-72 shrink-0 rounded-2xl bg-slate-900/30 border transition-all duration-200 ${
                    isOver
                      ? "border-indigo-500/50 bg-indigo-950/10 shadow-lg shadow-indigo-500/5"
                      : "border-white/5 bg-slate-900/20"
                  }`}
                >
                  {/* Column Header */}
                  <div className="p-3.5 border-b border-white/5 flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                      {col.replace("_", " ")}
                    </span>
                    <span className="text-xs px-2 py-0.5 bg-slate-800 text-slate-400 rounded-full font-bold">
                      {filteredList.length}
                    </span>
                  </div>

                  {/* Cards Queue */}
                  <div className="flex-1 p-3 flex flex-col gap-3 overflow-y-auto min-h-[400px]">
                    {filteredList.length === 0 ? (
                      <div className="flex-1 flex items-center justify-center p-8 text-center text-slate-600 text-xs italic">
                        Empty column
                      </div>
                    ) : (
                      filteredList.map((job) => {
                        const isLeadTech = job.technicians.find((t) => t.is_lead);

                        return (
                          <div
                            key={job.id}
                            draggable
                            onDragStart={() => handleDragStart(job.id)}
                            onClick={() => loadJobDetail(job.id)}
                            className={`glass-card p-3 rounded-xl border border-white/5 bg-slate-900/40 hover:bg-slate-900/60 active:cursor-grabbing hover:border-white/15 cursor-pointer relative flex flex-col gap-2.5 transition-all duration-150 ${
                              activeJobId === job.id ? "border-indigo-500/50 ring-1 ring-indigo-500/30" : ""
                            }`}
                          >
                            {/* Card Top: Trade Icon, Job Number & Priority */}
                            <div className="flex items-start justify-between">
                              <div className="flex items-center gap-1.5">
                                <span className="text-[10px] font-extrabold text-indigo-400 uppercase bg-indigo-500/10 px-1.5 py-0.5 rounded">
                                  {job.trade}
                                </span>
                                <span className="text-[11px] font-semibold text-slate-200">
                                  {job.job_number}
                                </span>
                              </div>
                              <span
                                className={`text-[9px] font-bold border px-1.5 py-0.5 rounded uppercase tracking-wide ${getPriorityBadgeColor(
                                  job.priority
                                )}`}
                              >
                                {job.priority}
                              </span>
                            </div>

                            {/* Job problem details */}
                            <p className="text-xs font-semibold text-slate-300 line-clamp-2 leading-relaxed">
                              {job.reported_problem || "No problem statement listed."}
                            </p>

                            {/* Scheduled hours */}
                            <div className="flex items-center gap-1.5 text-[10px] text-slate-400">
                              <Clock className="w-3.5 h-3.5 text-indigo-400/80" />
                              <span>
                                {job.scheduled_start
                                  ? new Date(job.scheduled_start).toLocaleTimeString(undefined, {
                                      hour: "2-digit",
                                      minute: "2-digit"
                                    })
                                  : "Unscheduled"}
                              </span>
                            </div>

                            {/* Divider */}
                            <div className="border-t border-white/5 my-0.5" />

                            {/* Customer information */}
                            {job.customer && (
                              <div className="flex flex-col gap-0.5 text-[10px] text-slate-400">
                                <p className="font-bold text-slate-300">
                                  {job.customer.first_name} {job.customer.last_name}
                                </p>
                                <div className="flex items-start gap-1 mt-0.5">
                                  <MapPin className="w-3 h-3 text-slate-500 shrink-0 mt-0.5" />
                                  <span className="truncate">
                                    {job.customer.address_line1}, {job.customer.city}
                                  </span>
                                </div>
                              </div>
                            )}

                            {/* Technician Tag */}
                            {isLeadTech && (
                              <div className="flex items-center gap-1.5 mt-1 self-start bg-indigo-500/10 border border-indigo-500/15 px-2 py-0.5 rounded-lg">
                                <UserIcon className="w-3 h-3 text-indigo-400" />
                                <span className="text-[10px] font-bold text-indigo-300">
                                  {isLeadTech.full_name}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            }
          )}
        </main>

        {/* RIGHT PANEL: Slide-in details sheet */}
        {activeJobId && (
          <aside className="w-[380px] border-l border-white/5 bg-slate-900/40 p-5 flex flex-col gap-5 overflow-y-auto shadow-2xl relative animate-in slide-in-from-right duration-200">
            {isDetailLoading ? (
              <div className="flex-1 flex flex-col items-center justify-center text-slate-500 text-xs">
                <div className="w-8 h-8 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></div>
                <span className="mt-4 font-semibold text-slate-400">Resolving work order...</span>
              </div>
            ) : activeJobDetail ? (
              <>
                {/* Header detail */}
                <div className="flex items-center justify-between pb-3 border-b border-white/5">
                  <div>
                    <h3 className="text-sm font-bold text-slate-400 uppercase tracking-wider">
                      Work Order Details
                    </h3>
                    <p className="text-base font-extrabold text-slate-200 mt-1">
                      {activeJobDetail.job_number}
                    </p>
                  </div>
                  <button
                    onClick={() => setActiveJobId(null)}
                    className="p-1.5 hover:bg-white/5 rounded-lg text-slate-400 hover:text-white"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Main status indicator */}
                <div className="flex flex-col gap-2 p-3 bg-slate-900/60 rounded-xl border border-white/5">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-400 font-medium">Status</span>
                    <span className="font-extrabold uppercase text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">
                      {activeJobDetail.status.replace("_", " ")}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs mt-1">
                    <span className="text-slate-400 font-medium">Trade Specialty</span>
                    <span className="font-semibold text-slate-200 uppercase">
                      {activeJobDetail.trade}
                    </span>
                  </div>
                  <div className="flex justify-between text-xs mt-1">
                    <span className="text-slate-400 font-medium">Priority</span>
                    <span className="font-semibold text-slate-200 capitalize">
                      {activeJobDetail.priority}
                    </span>
                  </div>
                </div>

                {/* Customer card */}
                {activeJobDetail.customer && (
                  <div className="flex flex-col gap-3 p-3.5 bg-slate-900/40 border border-white/5 rounded-xl">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                        Client Information
                      </span>
                      <button
                        onClick={() => loadCustomerHistory(activeJobDetail.customer!.id)}
                        className="text-[10px] font-bold text-indigo-400 hover:underline cursor-pointer flex items-center gap-1"
                      >
                        <FileText className="w-3.5 h-3.5" />
                        <span>View History</span>
                      </button>
                    </div>

                    <div className="flex flex-col gap-2 text-xs">
                      <p className="font-bold text-sm text-slate-200">
                        {activeJobDetail.customer.first_name} {activeJobDetail.customer.last_name}
                      </p>
                      <div className="flex items-center gap-2 text-slate-400">
                        <MapPin className="w-4 h-4 text-slate-500 shrink-0" />
                        <span>
                          {activeJobDetail.customer.address_line1}
                          {activeJobDetail.customer.address_line2 &&
                            `, ${activeJobDetail.customer.address_line2}`}
                          <br />
                          {activeJobDetail.customer.city}, {activeJobDetail.customer.state}{" "}
                          {activeJobDetail.customer.zip}
                        </span>
                      </div>
                      {activeJobDetail.customer.phone && (
                        <div className="flex items-center gap-2 text-slate-400">
                          <Phone className="w-4 h-4 text-slate-500" />
                          <span>{activeJobDetail.customer.phone}</span>
                        </div>
                      )}
                      {activeJobDetail.customer.email && (
                        <div className="flex items-center gap-2 text-slate-400">
                          <Mail className="w-4 h-4 text-slate-500" />
                          <span className="truncate">{activeJobDetail.customer.email}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Problem reported */}
                <div className="flex flex-col gap-1.5">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    Customer Reported Problem
                  </h4>
                  <div className="p-3 bg-slate-900/60 border border-white/5 rounded-xl text-xs text-slate-300 leading-relaxed font-medium">
                    {activeJobDetail.reported_problem || "No reported issues."}
                  </div>
                </div>

                {/* Dispatcher internal notes */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                      Dispatcher Notes (Internal)
                    </h4>
                    {!isEditingNotes && (
                      <button
                        onClick={() => setIsEditingNotes(true)}
                        className="text-[10px] font-bold text-indigo-400 hover:underline cursor-pointer"
                      >
                        Edit
                      </button>
                    )}
                  </div>
                  {isEditingNotes ? (
                    <div className="flex flex-col gap-2">
                      <textarea
                        value={tempNotesText}
                        onChange={(e) => setTempNotesText(e.target.value)}
                        className="w-full p-2.5 text-xs bg-slate-900 border border-indigo-500/30 rounded-xl text-slate-200 outline-none focus:border-indigo-500 min-h-[80px]"
                      />
                      <div className="flex items-center gap-2 self-end">
                        <button
                          onClick={() => {
                            setIsEditingNotes(false);
                            setTempNotesText(activeJobDetail.dispatcher_notes || "");
                          }}
                          className="px-2.5 py-1 text-[10px] font-bold bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={handleSaveNotes}
                          disabled={isActionLoading}
                          className="px-2.5 py-1 text-[10px] font-bold bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg"
                        >
                          Save
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-3 bg-slate-900/30 border border-dashed border-white/5 rounded-xl text-xs text-slate-400 italic">
                      {activeJobDetail.dispatcher_notes || "No notes logged yet."}
                    </div>
                  )}
                </div>

                {/* Technician assignment controls */}
                <div className="flex flex-col gap-3.5 border-t border-white/5 pt-4">
                  <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    Technician Assignment
                  </h4>

                  {/* Dropdown list */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] text-slate-500 font-bold uppercase">
                      Select Lead Technician
                    </label>
                    <select
                      value={activeJobDetail.technicians.find((t) => t.is_lead)?.tech_id || ""}
                      onChange={(e) => handleAssignTechDirect(e.target.value)}
                      className="w-full p-2 bg-slate-900 border border-white/5 text-xs text-slate-200 rounded-xl outline-none focus:border-indigo-500/50"
                    >
                      <option value="">-- Unassigned --</option>
                      {techs.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.full_name} ({t.availability_status})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* AI Suggestion Box */}
                  {aiSuggestion && (
                    <div className="p-3 bg-indigo-950/20 border border-indigo-500/20 rounded-xl flex items-start gap-3">
                      <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 shrink-0">
                        <Bot className="w-4 h-4" />
                      </div>
                      <div className="flex-1 flex flex-col gap-1.5">
                        <div className="flex items-center gap-1 text-[10px] text-indigo-300 font-extrabold uppercase tracking-wider">
                          <Sparkles className="w-3.5 h-3.5 animate-pulse" />
                          <span>AI Smart Dispatch Suggestion</span>
                        </div>
                        <p className="text-[11px] text-slate-300 leading-normal font-medium">
                          {aiSuggestion.reasoning}
                        </p>
                        {aiSuggestion.suggested_tech_id &&
                          activeJobDetail.technicians.find((t) => t.is_lead)?.tech_id !==
                            aiSuggestion.suggested_tech_id && (
                            <button
                              onClick={() => handleAssignTechDirect(aiSuggestion.suggested_tech_id!)}
                              className="mt-1 self-start px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-[10px] font-bold rounded-lg transition"
                            >
                              Assign {techs.find((t) => t.id === aiSuggestion.suggested_tech_id)?.full_name || "Suggested Tech"}
                            </button>
                          )}
                      </div>
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500 text-xs">
                Job not found or deleted
              </div>
            )}
          </aside>
        )}
      </div>

      {/* MODAL: Customer History Overlay */}
      {customerHistoryId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="glass-card w-full max-w-2xl rounded-2xl overflow-hidden shadow-2xl border border-white/10 animate-in zoom-in-95 duration-150">
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-slate-900/60">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-400" />
                <h3 className="font-bold text-slate-200">Customer History & Job Records</h3>
              </div>
              <button
                onClick={() => setCustomerHistoryId(null)}
                className="p-1 hover:bg-white/5 rounded text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-5 max-h-[480px] overflow-y-auto">
              {isHistoryLoading ? (
                <div className="py-12 flex flex-col items-center justify-center text-slate-500 text-xs">
                  <div className="w-8 h-8 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin"></div>
                  <span className="mt-4">Loading client historical data...</span>
                </div>
              ) : customerHistoryData ? (
                <div className="flex flex-col gap-5">
                  {/* Customer Card */}
                  <div className="grid grid-cols-2 gap-4 p-3 bg-slate-900/40 rounded-xl text-xs">
                    <div>
                      <p className="text-[10px] text-slate-500 font-bold uppercase">Name</p>
                      <p className="font-bold text-slate-200 mt-0.5">
                        {customerHistoryData.first_name} {customerHistoryData.last_name}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-slate-500 font-bold uppercase">Contact</p>
                      <p className="text-slate-300 mt-0.5">{customerHistoryData.phone || "No phone"}</p>
                      <p className="text-slate-400 mt-0.5">{customerHistoryData.email || "No email"}</p>
                    </div>
                  </div>

                  {/* History Jobs List */}
                  <div>
                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2.5">
                      Jobs List ({customerHistoryData.jobs?.length || 0})
                    </h4>
                    {customerHistoryData.jobs?.length === 0 ? (
                      <div className="p-6 text-center text-slate-500 italic text-xs border border-dashed border-white/5 rounded-xl">
                        No historical jobs registered for this customer.
                      </div>
                    ) : (
                      <div className="flex flex-col gap-3">
                        {customerHistoryData.jobs.map((hj: any) => (
                          <div
                            key={hj.id}
                            className="p-3 bg-slate-900/60 border border-white/5 rounded-xl flex items-center justify-between text-xs hover:border-white/10 transition"
                          >
                            <div className="flex flex-col gap-1">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-slate-200">{hj.job_number}</span>
                                <span className="text-[9px] bg-slate-800 text-slate-400 px-1 rounded uppercase">
                                  {hj.trade}
                                </span>
                                <span className="text-[9px] bg-slate-800 text-slate-400 px-1 rounded capitalize">
                                  {hj.job_type}
                                </span>
                              </div>
                              <p className="text-[10px] text-slate-400">
                                {hj.scheduled_start
                                  ? new Date(hj.scheduled_start).toLocaleDateString(undefined, {
                                      month: "short",
                                      day: "numeric",
                                      year: "numeric"
                                    })
                                  : "Unscheduled"}
                              </p>
                            </div>
                            <div className="text-right">
                              <span className="font-semibold text-indigo-400 uppercase tracking-wide bg-indigo-500/10 px-2 py-0.5 rounded text-[10px]">
                                {hj.status.replace("_", " ")}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="py-6 text-center text-rose-400 text-xs font-semibold">
                  Failed to load customer profile details.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Create Job */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <form
            onSubmit={handleCreateJobSubmit}
            className="glass-card w-full max-w-2xl rounded-2xl overflow-hidden shadow-2xl border border-white/10 animate-in zoom-in-95 duration-150 flex flex-col"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/5 flex items-center justify-between bg-slate-900/60">
              <h3 className="font-bold text-slate-200">Create New Job Order</h3>
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(false)}
                className="p-1 hover:bg-white/5 rounded text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Form Body */}
            <div className="p-5 max-h-[460px] overflow-y-auto flex flex-col gap-4 text-xs">
              {/* 1. Customer Section */}
              <div className="flex flex-col gap-2 p-3 bg-slate-900/40 border border-white/5 rounded-xl">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-300 uppercase tracking-wider text-[10px]">
                    Customer Selection
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreatingNewCustomer(!isCreatingNewCustomer);
                      setSelectedCustomer(null);
                    }}
                    className="text-[10px] font-bold text-indigo-400 hover:underline cursor-pointer"
                  >
                    {isCreatingNewCustomer ? "Select Existing Customer" : "Create New Customer"}
                  </button>
                </div>

                {isCreatingNewCustomer ? (
                  /* New Customer Fields */
                  <div className="grid grid-cols-2 gap-3 mt-2">
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        First Name
                      </label>
                      <input
                        type="text"
                        required
                        value={newCustFirst}
                        onChange={(e) => setNewCustFirst(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        Last Name
                      </label>
                      <input
                        type="text"
                        required
                        value={newCustLast}
                        onChange={(e) => setNewCustLast(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        Email
                      </label>
                      <input
                        type="email"
                        value={newCustEmail}
                        onChange={(e) => setNewCustEmail(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        Phone
                      </label>
                      <input
                        type="tel"
                        value={newCustPhone}
                        onChange={(e) => setNewCustPhone(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div className="col-span-2">
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        Address
                      </label>
                      <input
                        type="text"
                        value={newCustAddr}
                        onChange={(e) => setNewCustAddr(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        City
                      </label>
                      <input
                        type="text"
                        value={newCustCity}
                        onChange={(e) => setNewCustCity(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                        State
                      </label>
                      <input
                        type="text"
                        value={newCustState}
                        onChange={(e) => setNewCustState(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>
                  </div>
                ) : (
                  /* Existing Customer Search */
                  <div className="flex flex-col gap-2 mt-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                      <input
                        type="text"
                        placeholder="Type customer name, phone, or email..."
                        value={customerSearchQuery}
                        onChange={(e) => setCustomerSearchQuery(e.target.value)}
                        className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50 outline-none"
                      />
                    </div>

                    {searchedCustomers.length > 0 && (
                      <div className="max-h-32 overflow-y-auto border border-white/5 rounded-lg bg-slate-950/80 flex flex-col divide-y divide-white/5">
                        {searchedCustomers.map((c) => (
                          <div
                            key={c.id}
                            onClick={() => {
                              setSelectedCustomer(c);
                              setCustomerSearchQuery("");
                              setSearchedCustomers([]);
                            }}
                            className="p-2 hover:bg-indigo-600/10 cursor-pointer flex justify-between"
                          >
                            <span className="font-bold text-slate-300">
                              {c.first_name} {c.last_name}
                            </span>
                            <span className="text-slate-500 truncate">{c.email || c.phone}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {selectedCustomer && (
                      <div className="p-2.5 bg-indigo-950/20 border border-indigo-500/20 rounded-lg flex items-center justify-between">
                        <div>
                          <p className="font-bold text-indigo-300">
                            Selected: {selectedCustomer.first_name} {selectedCustomer.last_name}
                          </p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            {selectedCustomer.address_line1}, {selectedCustomer.city}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setSelectedCustomer(null)}
                          className="p-1 text-slate-400 hover:text-white"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* 2. Job Information */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    Trade
                  </label>
                  <select
                    value={jobTrade}
                    onChange={(e) => setJobTrade(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200"
                  >
                    <option value="hvac">HVAC</option>
                    <option value="garage_door">Garage Door</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    Job Type
                  </label>
                  <select
                    value={jobType}
                    onChange={(e) => setJobType(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200"
                  >
                    <option value="service">Service</option>
                    <option value="maintenance">Maintenance</option>
                    <option value="install">Install</option>
                    <option value="warranty">Warranty</option>
                    <option value="followup">Follow Up</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    Priority
                  </label>
                  <select
                    value={jobPriority}
                    onChange={(e) => setJobPriority(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200"
                  >
                    <option value="routine">Routine</option>
                    <option value="urgent">Urgent</option>
                    <option value="emergency">Emergency</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    Assign Technician
                  </label>
                  <select
                    value={jobTechId}
                    onChange={(e) => setJobTechId(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200 font-medium"
                  >
                    <option value="">-- Unassigned --</option>
                    {techs.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.full_name} ({t.availability_status})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* 3. Scheduling */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    Start Window Date/Time
                  </label>
                  <input
                    type="datetime-local"
                    value={jobStart}
                    onChange={(e) => setJobStart(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-slate-500 font-bold uppercase mb-1">
                    End Window Date/Time
                  </label>
                  <input
                    type="datetime-local"
                    value={jobEnd}
                    onChange={(e) => setJobEnd(e.target.value)}
                    className="w-full p-2 bg-slate-900 border border-white/5 rounded-lg text-slate-200 focus:border-indigo-500/50"
                  />
                </div>
              </div>

              {/* 4. Text Description */}
              <div className="flex flex-col gap-1.5">
                <label className="block text-[10px] text-slate-500 font-bold uppercase">
                  Problem Description
                </label>
                <textarea
                  value={jobProblem}
                  onChange={(e) => setJobProblem(e.target.value)}
                  placeholder="Describe the client's request or machinery issues..."
                  className="w-full p-2.5 bg-slate-900 border border-white/5 rounded-lg text-slate-200 outline-none focus:border-indigo-500/50 min-h-[60px]"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="block text-[10px] text-slate-500 font-bold uppercase">
                  Dispatcher Internal Notes
                </label>
                <textarea
                  value={jobNotes}
                  onChange={(e) => setJobNotes(e.target.value)}
                  placeholder="Internal routing details, gate codes, etc..."
                  className="w-full p-2.5 bg-slate-900 border border-white/5 rounded-lg text-slate-200 outline-none focus:border-indigo-500/50 min-h-[60px]"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-4 border-t border-white/5 flex items-center justify-end gap-3 bg-slate-900/60">
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isActionLoading}
                className="px-4 py-2 text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl shadow-lg shadow-indigo-600/10"
              >
                {isActionLoading ? "Creating..." : "Save Job Order"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
