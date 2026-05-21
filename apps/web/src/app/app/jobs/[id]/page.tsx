"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "../../../../hooks/useAuth";
import { AuthGuard } from "../../../../components/AuthGuard";
import {
  ArrowLeft,
  Clock,
  User,
  MapPin,
  Phone,
  Navigation,
  Plus,
  Trash2,
  Camera,
  Check,
  Loader2,
  Flame,
  Wrench,
  History,
  DollarSign,
  AlertCircle,
  ExternalLink,
  FileText,
  MessageSquare,
  AlertTriangle,
  Play,
  CheckCircle2,
  Pause,
  XCircle,
  Bot,
  ChevronRight,
  Sparkles
} from "lucide-react";

export default function JobCardScreen() {
  return (
    <AuthGuard>
      <JobCardContent />
    </AuthGuard>
  );
}

// Interfaces
interface Tech {
  id: string;
  tech_id: string;
  is_lead: boolean;
  full_name: string;
}

interface Photo {
  id: string;
  photo_type: string;
  cdn_url: string;
  caption: string | null;
  taken_at: string;
}

interface Note {
  id: string;
  author_id: string;
  note_type: string;
  body: string;
  is_internal: boolean;
  created_at: string;
}

interface Part {
  id: string;
  name: string;
  quantity: number;
  price_cents: number;
  serial_number: string | null;
}

interface StatusHistory {
  id: string;
  from_status: string | null;
  to_status: string;
  changed_by: string;
  changed_by_name?: string;
  changed_at: string;
  note: string | null;
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
  arrived_at: string | null;
  completed_at: string | null;
  customer: {
    id: string;
    first_name: string;
    last_name: string;
    email: string | null;
    phone: string | null;
    address_line1: string;
    address_line2: string | null;
    city: string;
    state: string;
    zip: string;
  };
  equipment: {
    id: string;
    name: string;
    make: string | null;
    model: string | null;
    serial_number: string | null;
    location: string | null;
  } | null;
  technicians: Tech[];
  photos: Photo[];
  notes: Note[];
  parts: Part[];
  status_history: StatusHistory[];
}

function JobCardContent() {
  const params = useParams();
  const router = useRouter();
  const { accessToken } = useAuth();
  const id = params.id as string;

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // State Management
  const [job, setJob] = useState<Job | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"details" | "notes" | "photos" | "parts">("details");

  // Status transition states
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [selectedNextStatus, setSelectedNextStatus] = useState<string | null>(null);
  const [statusNote, setStatusNote] = useState("");

  // Sub-resource addition states
  const [newNote, setNewNote] = useState("");
  const [isAddingNote, setIsAddingNote] = useState(false);

  // Photos state
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);
  const [photoCaption, setPhotoCaption] = useState("");
  const [photoType, setPhotoType] = useState("general");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Parts state
  const [showPartForm, setShowPartForm] = useState(false);
  const [partName, setPartName] = useState("");
  const [partQty, setPartQty] = useState(1);
  const [partPrice, setPartPrice] = useState("");
  const [partSerial, setPartSerial] = useState("");
  const [isAddingPart, setIsAddingPart] = useState(false);

  // Fetch job details
  const fetchJobDetails = async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_URL}/jobs/${id}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) {
        if (res.status === 404) throw new Error("Job not found");
        if (res.status === 403) throw new Error("Access denied. You are not assigned to this job.");
        throw new Error("Failed to load job details");
      }
      const data = await res.json();
      setJob(data);
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchJobDetails();
  }, [id, accessToken]);

  // Handle status transitions
  const handleTransition = async (nextStatus: string, note?: string) => {
    if (!accessToken || !job) return;
    setIsTransitioning(true);
    try {
      const res = await fetch(`${API_URL}/jobs/${job.id}/status`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ status: nextStatus, note: note || null })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Transition failed");
      }
      const updatedJob = await res.json();
      setJob(updatedJob);
      setShowStatusModal(false);
      setStatusNote("");
    } catch (err: any) {
      alert(`Error updating status: ${err.message}`);
    } finally {
      setIsTransitioning(false);
    }
  };

  // Add notes
  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !job || !newNote.trim()) return;
    setIsAddingNote(true);
    try {
      const res = await fetch(`${API_URL}/jobs/${job.id}/notes`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ body: newNote, note_type: "general" })
      });
      if (!res.ok) throw new Error("Failed to add note");
      const updatedJob = await res.json();
      setJob(updatedJob);
      setNewNote("");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsAddingNote(false);
    }
  };

  // Add parts
  const handleAddPart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken || !job || !partName.trim()) return;
    setIsAddingPart(true);
    try {
      const priceCents = Math.round(parseFloat(partPrice || "0") * 100);
      const res = await fetch(`${API_URL}/jobs/${job.id}/parts`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          name: partName,
          quantity: partQty,
          price_cents: priceCents,
          serial_number: partSerial || null
        })
      });
      if (!res.ok) throw new Error("Failed to add part");
      const updatedJob = await res.json();
      setJob(updatedJob);
      setPartName("");
      setPartQty(1);
      setPartPrice("");
      setPartSerial("");
      setShowPartForm(false);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsAddingPart(false);
    }
  };

  // Delete parts
  const handleDeletePart = async (partId: string) => {
    if (!accessToken || !job || !confirm("Are you sure you want to remove this part?")) return;
    try {
      const res = await fetch(`${API_URL}/jobs/${job.id}/parts/${partId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) throw new Error("Failed to remove part");
      const updatedJob = await res.json();
      setJob(updatedJob);
    } catch (err: any) {
      alert(err.message);
    }
  };

  // Delete photo
  const handleDeletePhoto = async (photoId: string) => {
    if (!accessToken || !job || !confirm("Are you sure you want to delete this photo?")) return;
    try {
      const res = await fetch(`${API_URL}/jobs/${job.id}/photos/${photoId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) throw new Error("Failed to delete photo");
      
      const jobRes = await fetch(`${API_URL}/jobs/${job.id}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!jobRes.ok) throw new Error("Failed to refresh job details");
      const updatedJob = await jobRes.json();
      setJob(updatedJob);
    } catch (err: any) {
      alert(err.message);
    }
  };

  // Handle Photo Upload
  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !accessToken || !job) return;
    setIsUploadingPhoto(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("photo_type", photoType);
      if (photoCaption.trim()) {
        formData.append("caption", photoCaption);
      }

      const res = await fetch(`${API_URL}/jobs/${job.id}/photos`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData
      });
      if (!res.ok) throw new Error("Failed to upload photo");
      const updatedJob = await res.json();
      setJob(updatedJob);
      setPhotoCaption("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  // Maps Navigation URL Generator
  const getNavUrl = (c: Job["customer"]) => {
    const addr = `${c.address_line1}, ${c.city}, ${c.state} ${c.zip}`;
    return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(addr)}`;
  };

  // Determine current Primary Action CTA
  const getStatusActionConfig = (status: string) => {
    switch (status) {
      case "scheduled":
        return { label: "Confirm Appointment", next: "confirmed", color: "bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/25", icon: <CheckCircle2 className="w-4 h-4" /> };
      case "confirmed":
        return { label: "Start Travel / En Route", next: "en_route", color: "bg-purple-650 hover:bg-purple-600 shadow-purple-600/25", icon: <Navigation className="w-4 h-4" /> };
      case "en_route":
        return { label: "Mark On Site", next: "on_site", color: "bg-indigo-650 hover:bg-indigo-600 shadow-indigo-600/25", icon: <MapPin className="w-4 h-4" /> };
      case "on_site":
        return { label: "Start Job / In Progress", next: "in_progress", color: "bg-blue-600 hover:bg-blue-550 shadow-blue-500/25", icon: <Play className="w-4 h-4 fill-current" /> };
      case "in_progress":
        return { label: "Complete Job", next: "completed", color: "bg-emerald-600 hover:bg-emerald-550 shadow-emerald-500/25", icon: <Check className="w-4 h-4 stroke-[3px]" /> };
      case "parts_needed":
      case "paused":
        return { label: "Resume Work", next: "in_progress", color: "bg-blue-600 hover:bg-blue-550 shadow-blue-500/25", icon: <Play className="w-4 h-4 fill-current" /> };
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
          <p className="text-slate-400 text-xs font-semibold">Loading job card...</p>
        </div>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4 animate-pulse" />
        <h3 className="text-white font-extrabold text-base mb-2">Error Loading Job</h3>
        <p className="text-slate-400 text-xs max-w-sm mb-6 leading-relaxed">{error || "Could not retrieve details."}</p>
        <button
          onClick={() => router.push("/app/home")}
          className="bg-slate-900 border border-slate-800 text-indigo-400 px-5 py-2.5 rounded-xl font-bold text-xs cursor-pointer hover:bg-slate-850 transition"
        >
          Return to Dashboard
        </button>
      </div>
    );
  }

  const isEmergency = job.priority === "emergency";
  const isUrgent = job.priority === "urgent";
  const isHVAC = job.trade === "hvac";
  const actionConfig = getStatusActionConfig(job.status);

  return (
    <div className="min-h-screen bg-slate-950 text-white flex justify-center selection:bg-indigo-500 selection:text-white pb-24">
      {/* Mobile container constraint */}
      <main className="w-full max-w-[480px] bg-slate-950/70 min-h-screen border-x border-slate-900/60 flex flex-col pb-16">
        
        {/* Sub-Header / Back button */}
        <div className="sticky top-0 bg-slate-950/85 backdrop-blur-md z-40 border-b border-slate-900/60 p-4 flex items-center justify-between">
          <button
            onClick={() => router.push("/app/home")}
            className="flex items-center gap-1.5 text-slate-400 hover:text-white border-none bg-transparent font-semibold text-xs cursor-pointer transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Dashboard</span>
          </button>
          
          <div className="flex gap-2">
            <span className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase border ${
              isEmergency ? "bg-red-500/10 border-red-500/20 text-red-400" :
              isUrgent ? "bg-amber-500/10 border-amber-500/20 text-amber-400" :
              "bg-emerald-500/10 border-emerald-500/20 text-emerald-450"
            }`}>
              {job.priority}
            </span>
            <span className={`text-[9px] px-2 py-0.5 rounded font-bold uppercase border capitalize ${
              job.status === "completed" ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-450" :
              job.status === "in_progress" ? "bg-blue-500/10 border-blue-500/20 text-blue-455" :
              job.status === "en_route" ? "bg-purple-500/10 border-purple-500/20 text-purple-400" :
              "bg-slate-800/50 border-slate-700 text-slate-450"
            }`}>
              {job.status.replace("_", " ")}
            </span>
          </div>
        </div>

        {/* Hero Card */}
        <div className="p-4 flex flex-col gap-4">
          <div className="bg-slate-900/20 border border-slate-900 rounded-2xl p-5 flex flex-col gap-4 shadow-xl relative overflow-hidden">
            <div className="flex justify-between items-start">
              <div>
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Work Order</span>
                <h1 className="text-2xl font-black text-white tracking-tight mt-1">{job.job_number}</h1>
              </div>
              <div>
                {isHVAC ? (
                  <div className="flex items-center gap-1 bg-sky-500/10 px-2.5 py-1 rounded-lg text-sky-400 text-[10px] font-bold uppercase border border-sky-500/10">
                    <Flame className="w-3.5 h-3.5 rotate-180" />
                    <span>HVAC</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 bg-purple-500/10 px-2.5 py-1 rounded-lg text-purple-400 text-[10px] font-bold uppercase border border-purple-500/10">
                    <Wrench className="w-3.5 h-3.5" />
                    <span>Garage</span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 text-slate-400 text-xs border-t border-slate-900 pt-3">
              <Clock className="w-4 h-4 text-indigo-400" />
              <span className="font-semibold text-slate-300">
                {job.scheduled_start ? (
                  new Date(job.scheduled_start).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })
                ) : "Not Scheduled"}
                {job.scheduled_start && job.scheduled_end && (
                  ` @ ${new Date(job.scheduled_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - ${new Date(job.scheduled_end).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                )}
              </span>
            </div>
          </div>

          {/* Action Callouts (Primary Status Bar) */}
          {actionConfig && (
            <button
              onClick={() => {
                setSelectedNextStatus(actionConfig.next);
                setShowStatusModal(true);
              }}
              disabled={isTransitioning}
              className={`w-full py-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 text-white border-none shadow-lg transition duration-200 cursor-pointer ${actionConfig.color}`}
            >
              {isTransitioning ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                actionConfig.icon
              )}
              <span>{isTransitioning ? "Processing..." : actionConfig.label}</span>
            </button>
          )}

          {["completed", "invoiced", "paid"].includes(job.status) && (
            <button
              onClick={() => router.push(`/app/jobs/${job.id}/invoice`)}
              className="w-full py-4 rounded-xl font-bold text-xs flex items-center justify-center gap-2 text-white border-none shadow-lg transition duration-200 cursor-pointer bg-gradient-to-r from-indigo-500 to-purple-650 hover:from-indigo-600 hover:to-purple-700 shadow-indigo-500/25"
            >
              <FileText className="w-4 h-4" />
              <span>Review Invoice</span>
            </button>
          )}

          {/* Guided Inspection Entry Card */}
          {job.status === "in_progress" && (
            <div className="glass-card rounded-2xl p-5 border border-indigo-500/25 relative overflow-hidden my-2">
              <div className="absolute top-0 right-0 w-16 h-16 bg-indigo-500/10 rounded-full blur-lg pointer-events-none" />
              <div className="flex items-center gap-2 mb-2 text-indigo-400 font-bold text-xs uppercase tracking-wider">
                <Sparkles className="w-4 h-4 animate-pulse" />
                <span>Guided Inspection Engine</span>
              </div>
              <p className="text-xs text-slate-300 leading-relaxed mb-3">
                Follow the dynamic step-by-step diagnostic checklist to log photos, pressures, and run AI analysis models.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => router.push(`/app/jobs/${job.id}/inspection`)}
                  className="flex-1 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 text-white font-bold text-xs shadow-lg shadow-indigo-500/20 transition cursor-pointer flex items-center justify-center gap-1.5"
                >
                  <span>Launch Guided Inspection</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => router.push(`/app/jobs/${job.id}/ai?from=job_card`)}
                  className="py-3 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-800 text-indigo-400 font-bold text-xs transition cursor-pointer flex items-center justify-center gap-1.5"
                  title="Ask Senior Tech AI"
                >
                  <Bot className="w-4.5 h-4.5 animate-pulse" />
                  <span>Ask AI</span>
                </button>
              </div>
            </div>
          )}

          {/* Sub-Actions (Transitions like parts needed, pause, cancel, etc.) */}
          {job.status !== "completed" && job.status !== "cancelled" && (
            <div className="grid grid-cols-2 gap-2">
              {job.status === "in_progress" && (
                <>
                  <button
                    onClick={() => {
                      setSelectedNextStatus("parts_needed");
                      setShowStatusModal(true);
                    }}
                    className="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 text-amber-400 py-3 rounded-xl font-bold text-[10px] cursor-pointer transition flex items-center justify-center gap-1.5"
                  >
                    <Wrench className="w-3.5 h-3.5" />
                    Waiting on Parts
                  </button>
                  <button
                    onClick={() => {
                      setSelectedNextStatus("paused");
                      setShowStatusModal(true);
                    }}
                    className="bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 text-blue-400 py-3 rounded-xl font-bold text-[10px] cursor-pointer transition flex items-center justify-center gap-1.5"
                  >
                    <Pause className="w-3.5 h-3.5" />
                    Pause Work
                  </button>
                </>
              )}
              <button
                onClick={() => {
                  setSelectedNextStatus("follow_up_required");
                  setShowStatusModal(true);
                }}
                className="bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 text-indigo-400 py-3 rounded-xl font-bold text-[10px] cursor-pointer transition flex items-center justify-center gap-1.5"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                Follow-up Needed
              </button>
              <button
                onClick={() => {
                  if (confirm("Are you sure you want to cancel this job?")) {
                    handleTransition("cancelled", "Technician cancelled job");
                  }
                }}
                className="bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 py-3 rounded-xl font-bold text-[10px] cursor-pointer transition flex items-center justify-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                Cancel Job
              </button>
            </div>
          )}

          {/* Quick-links Customer & Navigation Section */}
          <div className="bg-slate-900/15 border border-slate-900/80 rounded-2xl p-4 flex flex-col gap-4">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Client</span>
                <h3 className="text-sm font-extrabold text-white mt-0.5">
                  {job.customer.first_name} {job.customer.last_name}
                </h3>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  {job.customer.address_line1} {job.customer.address_line2 ? `, ${job.customer.address_line2}` : ""}
                  <br />
                  {job.customer.city}, {job.customer.state} {job.customer.zip}
                </p>
              </div>

              {job.customer.phone && (
                <a
                  href={`tel:${job.customer.phone}`}
                  className="bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 p-2.5 rounded-full text-indigo-400 transition cursor-pointer flex items-center justify-center"
                >
                  <Phone className="w-4 h-4" />
                </a>
              )}
            </div>

            <a
              href={getNavUrl(job.customer)}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-slate-900 hover:bg-slate-850 border border-slate-800 text-indigo-400 py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 transition no-underline cursor-pointer"
            >
              <Navigation className="w-4 h-4 fill-current animate-bounce" />
              Navigate to Site
            </a>
          </div>

          {/* Tab Selection */}
          <div className="flex border-b border-slate-900 mt-4 overflow-x-auto gap-1 no-scrollbar">
            {[
              { id: "details", label: "Details" },
              { id: "notes", label: `Notes (${job.notes.length})` },
              { id: "photos", label: `Photos (${job.photos.length})` },
              { id: "parts", label: `Parts (${job.parts.length})` }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-2 px-3.5 text-xs font-bold whitespace-nowrap cursor-pointer transition border-b-2 bg-transparent ${
                  activeTab === tab.id
                    ? "border-indigo-400 text-indigo-400"
                    : "border-transparent text-slate-500 hover:text-slate-400"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab contents */}
          <div className="flex flex-col gap-4 mt-2">
            
            {/* DETAILS TAB */}
            {activeTab === "details" && (
              <div className="flex flex-col gap-4 animate-fadeIn">
                {/* Reported Problem */}
                <div className="bg-slate-900/10 border border-slate-900 rounded-xl p-4">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Problem Description</span>
                  <p className="text-xs text-slate-350 leading-relaxed font-medium">
                    {job.reported_problem || "No problem details provided by customer."}
                  </p>
                </div>

                {/* Dispatcher Notes */}
                {job.dispatcher_notes && (
                  <div className="bg-slate-900/10 border border-slate-900 rounded-xl p-4">
                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1">Dispatcher Notes</span>
                    <p className="text-xs text-slate-350 leading-relaxed italic">
                      {job.dispatcher_notes}
                    </p>
                  </div>
                )}

                {/* Equipment details */}
                <div className="bg-slate-900/10 border border-slate-900 rounded-xl p-4">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-2">Equipment Information</span>
                  {job.equipment ? (
                    <div className="flex flex-col gap-1.5 text-xs">
                      <div className="flex justify-between border-b border-slate-900 pb-1.5">
                        <span className="text-slate-500 font-semibold">Unit:</span>
                        <span className="text-white font-extrabold">{job.equipment.name}</span>
                      </div>
                      {(job.equipment.make || job.equipment.model) && (
                        <div className="flex justify-between border-b border-slate-900 pb-1.5">
                          <span className="text-slate-500 font-semibold">Model:</span>
                          <span className="text-white font-medium">
                            {job.equipment.make} {job.equipment.model}
                          </span>
                        </div>
                      )}
                      {job.equipment.serial_number && (
                        <div className="flex justify-between border-b border-slate-900 pb-1.5">
                          <span className="text-slate-500 font-semibold">Serial:</span>
                          <span className="text-white font-mono font-bold">{job.equipment.serial_number}</span>
                        </div>
                      )}
                      {job.equipment.location && (
                        <div className="flex justify-between">
                          <span className="text-slate-500 font-semibold">Location:</span>
                          <span className="text-white">{job.equipment.location}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 leading-normal">No equipment linked to this work order.</p>
                  )}
                </div>

                {/* Status History Logs */}
                <div className="bg-slate-900/10 border border-slate-900 rounded-xl p-4">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1 mb-3">
                    <History className="w-3.5 h-3.5 text-slate-500" />
                    Status History Log
                  </span>
                  <div className="flex flex-col gap-3 relative before:absolute before:left-2 before:top-2 before:bottom-2 before:w-[1px] before:bg-slate-850">
                    {job.status_history.map((sh, idx) => (
                      <div key={idx} className="flex gap-4 relative">
                        <div className="w-4 h-4 bg-slate-950 border-2 border-slate-800 rounded-full flex items-center justify-center z-10 shrink-0 mt-0.5">
                          <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full" />
                        </div>
                        <div className="flex-1 text-xs">
                          <div className="flex justify-between">
                            <span className="font-extrabold text-white capitalize">
                              {sh.to_status.replace("_", " ")}
                            </span>
                            <span className="text-[10px] text-slate-500">
                              {new Date(sh.changed_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                            </span>
                          </div>
                          <p className="text-[10px] text-slate-550 mt-0.5">
                            Changed by: {sh.changed_by_name || "System"}
                          </p>
                          {sh.note && (
                            <p className="bg-slate-900/60 p-2 border border-slate-900 rounded-lg text-[10px] text-slate-400 mt-1 leading-normal">
                              "{sh.note}"
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* NOTES TAB */}
            {activeTab === "notes" && (
              <div className="flex flex-col gap-4 animate-fadeIn">
                {/* AI diagnosis integration box */}
                {job.notes.some(n => n.note_type === "ai_summary") ? (
                  job.notes.filter(n => n.note_type === "ai_summary").map(aiNote => (
                    <div key={aiNote.id} className="bg-indigo-950/20 border border-indigo-900/50 rounded-xl p-4 relative overflow-hidden">
                      <div className="absolute right-0 top-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-2xl" />
                      <div className="flex items-center gap-1.5 mb-2">
                        <Bot className="w-4 h-4 text-indigo-400" />
                        <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest">AI Diagnostics Summary</span>
                      </div>
                      <p className="text-xs text-indigo-200/90 leading-relaxed font-medium">
                        {aiNote.body}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="bg-indigo-950/10 border border-indigo-950/40 rounded-xl p-4 flex items-center gap-3">
                    <Bot className="w-8 h-8 text-indigo-500 shrink-0 animate-pulse" />
                    <div>
                      <h4 className="text-xs font-bold text-white">Need diagnostic insights?</h4>
                      <p className="text-[10px] text-slate-400 mt-0.5">AI analysis will automatically compile once technician photos are uploaded.</p>
                    </div>
                  </div>
                )}

                {/* Add note input box */}
                <form onSubmit={handleAddNote} className="flex gap-2">
                  <input
                    type="text"
                    value={newNote}
                    onChange={e => setNewNote(e.target.value)}
                    placeholder="Type diagnostic notes..."
                    disabled={isAddingNote}
                    className="flex-1 bg-slate-900 border border-slate-800 text-white rounded-xl px-3 text-xs placeholder:text-slate-600 focus:outline-none focus:border-indigo-500"
                  />
                  <button
                    type="submit"
                    disabled={isAddingNote || !newNote.trim()}
                    className="bg-indigo-650 hover:bg-indigo-600 text-white p-2.5 rounded-xl transition cursor-pointer border-none flex items-center justify-center disabled:opacity-40"
                  >
                    {isAddingNote ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Plus className="w-4 h-4" />
                    )}
                  </button>
                </form>

                {/* Notes chronological feed */}
                <div className="flex flex-col gap-3">
                  {job.notes.filter(n => n.note_type !== "ai_summary").length === 0 ? (
                    <div className="p-8 text-center text-slate-500 text-xs">No technician notes logged yet.</div>
                  ) : (
                    job.notes
                      .filter(n => n.note_type !== "ai_summary")
                      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                      .map(note => (
                        <div key={note.id} className="bg-slate-900/20 border border-slate-900 rounded-xl p-3.5 flex flex-col gap-1.5 shadow">
                          <div className="flex justify-between items-center text-[10px] text-slate-500">
                            <span className="font-extrabold text-slate-350">
                              {note.note_type === "dispatch" ? "Dispatcher note" : "Technician note"}
                            </span>
                            <span>
                              {new Date(note.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}{" "}
                              {new Date(note.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
                            </span>
                          </div>
                          <p className="text-xs text-white leading-relaxed">{note.body}</p>
                        </div>
                      ))
                  )}
                </div>
              </div>
            )}

            {/* PHOTOS TAB */}
            {activeTab === "photos" && (
              <div className="flex flex-col gap-4 animate-fadeIn">
                {/* Upload Section */}
                <div className="bg-slate-900/10 border border-slate-900 rounded-xl p-4 flex flex-col gap-3">
                  <div className="flex gap-2">
                    <select
                      value={photoType}
                      onChange={e => setPhotoType(e.target.value)}
                      className="bg-slate-900 border border-slate-800 text-slate-300 rounded-xl px-2 text-xs font-bold focus:outline-none"
                    >
                      <option value="general">General</option>
                      <option value="nameplate">Nameplate</option>
                      <option value="fault">Fault / Issue</option>
                      <option value="before">Before Work</option>
                      <option value="after">After Work</option>
                    </select>

                    <input
                      type="text"
                      value={photoCaption}
                      onChange={e => setPhotoCaption(e.target.value)}
                      placeholder="Add caption..."
                      className="flex-1 bg-slate-900 border border-slate-800 text-white rounded-xl px-3 text-xs placeholder:text-slate-600 focus:outline-none"
                    />
                  </div>

                  <input
                    type="file"
                    ref={fileInputRef}
                    accept="image/*"
                    onChange={handlePhotoUpload}
                    className="hidden"
                  />

                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploadingPhoto}
                    className="bg-indigo-650 hover:bg-indigo-600 text-white py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-2 cursor-pointer transition border-none shadow-md shadow-indigo-650/10 disabled:opacity-40"
                  >
                    {isUploadingPhoto ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Camera className="w-4 h-4" />
                    )}
                    <span>{isUploadingPhoto ? "Uploading Photo..." : "Take or Upload Photo"}</span>
                  </button>
                </div>

                {/* Photo Gallery Grid */}
                {job.photos.length === 0 ? (
                  <div className="p-8 text-center text-slate-500 text-xs">No job photos uploaded yet.</div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    {job.photos.map(photo => (
                      <div key={photo.id} className="bg-slate-900/30 border border-slate-900 rounded-xl overflow-hidden shadow relative group flex flex-col">
                        <div className="relative aspect-square w-full bg-slate-950 flex items-center justify-center">
                          <img
                            src={photo.cdn_url}
                            alt={photo.caption || "Job Photo"}
                            className="object-cover w-full h-full"
                          />
                          <span className="absolute top-2 left-2 bg-slate-950/70 backdrop-blur-sm border border-slate-800 px-1.5 py-0.5 rounded text-[8px] font-extrabold uppercase tracking-wide">
                            {photo.photo_type}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleDeletePhoto(photo.id)}
                            className="absolute top-2 right-2 p-1 bg-rose-950/90 border border-rose-800 text-rose-300 rounded opacity-0 group-hover:opacity-100 hover:bg-rose-900 transition-opacity duration-200 shadow cursor-pointer"
                            title="Delete Photo"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                        {photo.caption && (
                          <div className="p-2 border-t border-slate-900 bg-slate-950/40">
                            <p className="text-[10px] text-slate-300 leading-snug">{photo.caption}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* PARTS TAB */}
            {activeTab === "parts" && (
              <div className="flex flex-col gap-4 animate-fadeIn">
                {/* Header list actions */}
                <div className="flex justify-between items-center">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Parts Logs</span>
                  <button
                    onClick={() => setShowPartForm(!showPartForm)}
                    className="bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 hover:bg-indigo-600/25 px-3 py-1.5 rounded-lg text-[10px] font-bold cursor-pointer transition flex items-center gap-1"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Part Log
                  </button>
                </div>

                {/* Parts Form */}
                {showPartForm && (
                  <form onSubmit={handleAddPart} className="bg-slate-900/15 border border-slate-900 rounded-xl p-4 flex flex-col gap-3 animate-[slideDown_0.2s_ease-out_forwards]">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="col-span-2">
                        <label className="text-[9px] font-bold text-slate-500 uppercase block mb-1">Part Name</label>
                        <input
                          type="text"
                          required
                          value={partName}
                          onChange={e => setPartName(e.target.value)}
                          placeholder="e.g. Capacitor 45uF"
                          className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div>
                        <label className="text-[9px] font-bold text-slate-500 uppercase block mb-1">Quantity</label>
                        <input
                          type="number"
                          required
                          min="1"
                          value={partQty}
                          onChange={e => setPartQty(parseInt(e.target.value))}
                          className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div>
                        <label className="text-[9px] font-bold text-slate-500 uppercase block mb-1">Price ($)</label>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          value={partPrice}
                          onChange={e => setPartPrice(e.target.value)}
                          placeholder="45.00"
                          className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-[9px] font-bold text-slate-500 uppercase block mb-1">Serial Number (Optional)</label>
                        <input
                          type="text"
                          value={partSerial}
                          onChange={e => setPartSerial(e.target.value)}
                          placeholder="e.g. CAP98235"
                          className="w-full bg-slate-950 border border-slate-800 text-white rounded-lg px-2.5 py-2 text-xs focus:outline-none focus:border-indigo-500"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={isAddingPart}
                      className="bg-indigo-650 hover:bg-indigo-600 text-white py-2.5 rounded-lg text-xs font-bold cursor-pointer transition border-none flex items-center justify-center gap-1.5 disabled:opacity-40"
                    >
                      {isAddingPart ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Check className="w-3.5 h-3.5" />
                      )}
                      <span>Add Part to Job</span>
                    </button>
                  </form>
                )}

                {/* Parts logged list */}
                <div className="flex flex-col gap-2">
                  {job.parts.length === 0 ? (
                    <div className="p-8 text-center text-slate-500 text-xs">No parts logged for this job yet.</div>
                  ) : (
                    job.parts.map(part => (
                      <div key={part.id} className="bg-slate-900/20 border border-slate-900 rounded-xl p-3.5 flex justify-between items-center shadow">
                        <div>
                          <h4 className="text-xs font-bold text-white leading-normal">{part.name}</h4>
                          <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-500">
                            <span className="bg-slate-950 px-1.5 py-0.5 rounded text-white font-bold">Qty: {part.quantity}</span>
                            <span>•</span>
                            <span className="text-slate-400">${(part.price_cents * part.quantity / 100).toFixed(2)}</span>
                            {part.serial_number && (
                              <>
                                <span>•</span>
                                <span className="font-mono text-slate-500">SN: {part.serial_number}</span>
                              </>
                            )}
                          </div>
                        </div>

                        <button
                          onClick={() => handleDeletePart(part.id)}
                          className="text-red-400 hover:text-red-300 border-none bg-transparent p-1.5 cursor-pointer transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Transition Dialog Overlay/Bottom-Sheet */}
        {showStatusModal && selectedNextStatus && (
          <div className="fixed inset-0 bg-black/65 z-[100] flex items-end justify-center">
            <div
              onClick={() => {
                setShowStatusModal(false);
                setStatusNote("");
              }}
              className="absolute inset-0 cursor-default"
            />

            <div className="relative bg-slate-950 border-t border-slate-800 rounded-t-2xl w-full max-w-[480px] p-5 flex flex-col gap-4 shadow-2xl z-10 animate-[slideUp_0.25s_cubic-bezier(0.16,1,0.3,1)_forwards]">
              <div className="flex justify-between items-center border-b border-slate-900 pb-3">
                <span className="font-extrabold text-sm text-white">
                  Confirm Transition to: <span className="capitalize text-indigo-400">{selectedNextStatus.replace("_", " ")}</span>
                </span>
                <button
                  onClick={() => {
                    setShowStatusModal(false);
                    setStatusNote("");
                  }}
                  className="text-slate-500 hover:text-slate-400 text-xs font-semibold cursor-pointer border-none bg-transparent"
                >
                  Cancel
                </button>
              </div>

              <div className="flex flex-col gap-3">
                <label className="text-[10px] font-bold text-slate-500 uppercase block">Add a transition note (Optional)</label>
                <textarea
                  rows={3}
                  value={statusNote}
                  onChange={e => setStatusNote(e.target.value)}
                  placeholder="e.g. Arrived on site, homeowner let me in."
                  className="w-full bg-slate-900 border border-slate-800 text-white rounded-xl p-3 text-xs placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 resize-none"
                />

                <button
                  onClick={() => handleTransition(selectedNextStatus, statusNote)}
                  disabled={isTransitioning}
                  className="bg-indigo-650 hover:bg-indigo-600 text-white py-3 rounded-xl font-bold text-xs flex items-center justify-center gap-1.5 cursor-pointer transition border-none shadow-md"
                >
                  {isTransitioning ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  <span>Transition Status</span>
                </button>
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
