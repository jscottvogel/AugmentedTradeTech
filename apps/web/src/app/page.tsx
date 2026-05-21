"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "../hooks/useAuth";
import { AuthGuard } from "../components/AuthGuard";
import { 
  LogOut, 
  User, 
  Phone, 
  Shield, 
  Plus, 
  X, 
  Building, 
  Briefcase, 
  Camera, 
  Users, 
  Check, 
  Info,
  ChevronRight,
  ShieldAlert,
  Loader2,
  Database
} from "lucide-react";

export default function HomePage() {
  return (
    <AuthGuard>
      <HomeContent />
    </AuthGuard>
  );
}

function HomeContent() {
  const { user, accessToken, logout, updateCurrentUser } = useAuth();
  
  // Profile completion form states
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [phone, setPhone] = useState(user?.phone || "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  
  // Tech specific completion states
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || "");
  const [trades, setTrades] = useState<string[]>([]);
  const [certInput, setCertInput] = useState("");
  const [certifications, setCertifications] = useState<string[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<string[]>([]);
  const [isUploadingPhoto, setIsUploadingPhoto] = useState(false);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Availability Bar States
  const [isAvailabilitySheetOpen, setIsAvailabilitySheetOpen] = useState(false);
  const [elapsedText, setElapsedText] = useState("");

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Fetch technician profile on mount if active
  useEffect(() => {
    if (user && user.is_active && user.role === "tech" && accessToken) {
      fetch(`${API_URL}/me/profile`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      })
      .then(res => {
        if (res.ok) return res.json();
        throw new Error("Failed to load profile details");
      })
      .then(data => {
        updateCurrentUser({ tech_profile: data.tech_profile, avatar_url: data.avatar_url });
      })
      .catch(err => console.error(err));
    }
  }, [user?.is_active, accessToken]);

  // Periodic heartbeat ping for active techs
  useEffect(() => {
    if (!user || !user.is_active || user.role !== "tech" || !accessToken) return;

    const sendHeartbeat = () => {
      fetch(`${API_URL}/me/heartbeat`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      }).catch(err => console.error("Heartbeat error:", err));
    };

    // Send immediately and then every 5 minutes
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
    const timerInterval = setInterval(updateTimer, 10000); // 10s updates
    return () => clearInterval(timerInterval);
  }, [user?.tech_profile?.status_changed_at]);

  // Photo upload trigger
  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !accessToken) return;

    setIsUploadingPhoto(true);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_URL}/me/profile/photo`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData
      });

      if (!res.ok) {
        throw new Error("Failed to upload profile photo");
      }

      const data = await res.json();
      setAvatarUrl(data.avatar_url);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsUploadingPhoto(false);
    }
  };

  const handleProfileCompleteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    if (!user) return;

    // Validation for passwords (Admins/Dispatchers only)
    const requiresPassword = user.role === "company_admin" || user.role === "dispatcher";
    if (requiresPassword) {
      if (!password) {
        setError("Password is required");
        setIsSubmitting(false);
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        setIsSubmitting(false);
        return;
      }
      if (password.length < 8) {
        setError("Password must be at least 8 characters long");
        setIsSubmitting(false);
        return;
      }
    }

    if (!fullName.trim()) {
      setError("Full name is required");
      setIsSubmitting(false);
      return;
    }

    try {
      // 1. Submit password/name updates to general profile/activation endpoint
      if (requiresPassword) {
        const res = await fetch(`${API_URL}/users/${user.id}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            full_name: fullName,
            phone: phone || undefined,
            password: password,
          }),
        });

        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Failed to complete profile configuration");
        }
        
        const updatedUser = await res.json();
        updateCurrentUser({
          is_active: true,
          full_name: updatedUser.full_name,
          phone: updatedUser.phone,
        });
      } else {
        // Technician Profile Setup Completion
        if (!avatarUrl) {
          setError("Profile photo is required for technicians");
          setIsSubmitting(false);
          return;
        }
        if (trades.length === 0) {
          setError("Please select at least one trade");
          setIsSubmitting(false);
          return;
        }
        if (certifications.length === 0) {
          setError("Please add at least one certification");
          setIsSubmitting(false);
          return;
        }
        if (selectedSkills.length === 0) {
          setError("Please select at least one skill");
          setIsSubmitting(false);
          return;
        }

        const res = await fetch(`${API_URL}/me/profile`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({
            full_name: fullName,
            phone: phone || undefined,
            avatar_url: avatarUrl,
            trades: trades,
            certifications: certifications.map(c => ({ name: c })),
            skills: selectedSkills,
          }),
        });

        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Failed to save technician profile");
        }

        const updatedMe = await res.json();
        updateCurrentUser({
          is_active: updatedMe.is_active,
          full_name: updatedMe.full_name,
          phone: updatedMe.phone,
          avatar_url: updatedMe.avatar_url,
          tech_profile: updatedMe.tech_profile,
        });
      }

    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdateAvailability = async (newStatus: string) => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_URL}/me/availability`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({ status: newStatus })
      });

      if (!res.ok) {
        throw new Error("Failed to update availability status");
      }

      const updatedMe = await res.json();
      updateCurrentUser({ tech_profile: updatedMe.tech_profile });
      setIsAvailabilitySheetOpen(false);
    } catch (err: any) {
      console.error(err.message);
    }
  };

  const addCertification = () => {
    if (certInput.trim() && !certifications.includes(certInput.trim())) {
      setCertifications([...certifications, certInput.trim()]);
      setCertInput("");
    }
  };

  const removeCertification = (cert: string) => {
    setCertifications(certifications.filter(c => c !== cert));
  };

  const toggleSkill = (skill: string) => {
    if (selectedSkills.includes(skill)) {
      setSelectedSkills(selectedSkills.filter(s => s !== skill));
    } else {
      setSelectedSkills([...selectedSkills, skill]);
    }
  };

  const skillOptions = [
    "Electrical Troubleshooting",
    "Gas Piping",
    "Refrigerant Handling (EPA)",
    "Ductwork Installation",
    "Spring Replacement",
    "Opener Programming",
    "Customer Support",
    "Safety Inspection"
  ];

  // Render Technician profile setup wizard (inactive tech)
  if (user && !user.is_active && user.role === "tech") {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 flex items-center justify-center p-6 font-sans text-slate-100">
        <div className="w-full max-w-xl bg-slate-900/40 backdrop-blur-lg border border-slate-800 rounded-2xl p-8 shadow-2xl flex flex-col">
          <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500 bg-clip-text text-transparent">
            Technician Setup
          </h2>
          <p className="text-sm text-slate-400 text-center mt-2 mb-6 leading-relaxed">
            Configure your technical expertise, certifications, and upload a profile photo to begin claiming jobs.
          </p>

          {error && (
            <div className="p-4 mb-6 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleProfileCompleteSubmit} className="space-y-6">
            
            {/* Photo Upload Section */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Profile Photo *</label>
              <div className="flex items-center gap-5 mt-1">
                {avatarUrl ? (
                  <img src={avatarUrl} alt="Avatar Preview" className="w-16 h-16 rounded-full object-cover border-2 border-indigo-500 shadow-md" />
                ) : (
                  <div className="w-16 h-16 rounded-full bg-slate-950 border-2 border-dashed border-slate-800 flex items-center justify-center">
                    <Camera className="w-6 h-6 text-slate-600" />
                  </div>
                )}
                <div>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handlePhotoUpload}
                    className="hidden"
                    id="tech-avatar-input"
                  />
                  <label htmlFor="tech-avatar-input" className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold rounded-lg cursor-pointer transition">
                    {isUploadingPhoto ? "Uploading..." : "Upload Photo"}
                  </label>
                  <p className="text-[11px] text-slate-500 mt-2">
                    JPG/PNG files up to 5MB
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Full Name *</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Full Name"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Phone Number *</label>
              <input
                type="tel"
                required
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 019-2834"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
              />
            </div>

            {/* Trades Cards */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Select Your Trade *</label>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: "HVAC", label: "HVAC", desc: "Heating & AC" },
                  { id: "Garage Door", label: "Garage Door", desc: "Springs & Rollers" },
                  { id: "Both", label: "Both", desc: "Multi-trade" },
                ].map((item) => {
                  const isActive = 
                    item.id === "Both" 
                      ? trades.includes("HVAC") && trades.includes("Garage Door")
                      : item.id === "HVAC"
                      ? trades.includes("HVAC") && !trades.includes("Garage Door")
                      : trades.includes("Garage Door") && !trades.includes("HVAC");
                  
                  return (
                    <div
                      key={item.id}
                      onClick={() => {
                        if (item.id === "Both") setTrades(["HVAC", "Garage Door"]);
                        else setTrades([item.id]);
                      }}
                      className={`p-3 rounded-xl border-2 text-center cursor-pointer transition-all flex flex-col justify-center ${
                        isActive 
                          ? "bg-indigo-500/10 border-indigo-500 shadow-md shadow-indigo-500/5" 
                          : "bg-slate-950/40 border-slate-800/80 hover:border-slate-700"
                      }`}
                    >
                      <span className="font-semibold text-xs text-white">{item.label}</span>
                      <span className="text-[10px] text-slate-500 mt-1">{item.desc}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Certifications tagging */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Certifications *</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={certInput}
                  onChange={(e) => setCertInput(e.target.value)}
                  placeholder="e.g. EPA 608 Type II"
                  className="flex-1 px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      addCertification();
                    }
                  }}
                />
                <button 
                  type="button" 
                  onClick={addCertification} 
                  className="px-4 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs rounded-xl cursor-pointer transition"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {certifications.map((cert) => (
                  <span key={cert} className="inline-flex items-center gap-1.5 px-3 py-1 bg-indigo-500/10 border border-indigo-500/20 rounded-full text-indigo-300 text-xs font-medium">
                    {cert}
                    <button type="button" onClick={() => removeCertification(cert)} className="text-red-400 hover:text-red-300 ml-0.5 text-sm font-bold cursor-pointer">
                      &times;
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Skills selection */}
            <div className="space-y-2">
              <label className="text-sm font-medium text-slate-300 block">Core Skills *</label>
              <div className="flex flex-wrap gap-2">
                {skillOptions.map((skill) => {
                  const isActive = selectedSkills.includes(skill);
                  return (
                    <span
                      key={skill}
                      onClick={() => toggleSkill(skill)}
                      className={`px-3 py-1.5 rounded-full border text-xs font-medium cursor-pointer transition ${
                        isActive
                          ? "bg-indigo-500/20 border-indigo-500 text-white shadow-sm"
                          : "bg-slate-950/40 border-slate-800/80 text-slate-400 hover:border-slate-700"
                      }`}
                    >
                      {skill}
                    </span>
                  );
                })}
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] text-white font-semibold text-sm rounded-xl cursor-pointer shadow-lg shadow-indigo-600/20 transition flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Finalizing Account...
                </>
              ) : (
                "Complete Profile Setup"
              )}
            </button>
            
            <button
              type="button"
              onClick={logout}
              className="w-full text-xs text-slate-500 hover:text-slate-400 underline transition cursor-pointer text-center"
            >
              Log out & Cancel
            </button>
          </form>
        </div>
      </div>
    );
  }

  // If user is invited/inactive (and not a tech), render the Admin/Dispatcher completion form
  if (user && !user.is_active) {
    const isPassRequired = user.role === "company_admin" || user.role === "dispatcher";

    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 flex items-center justify-center p-6 font-sans text-slate-100">
        <div className="w-full max-w-md bg-slate-900/40 backdrop-blur-lg border border-slate-800 rounded-2xl p-8 shadow-2xl flex flex-col">
          <h2 className="text-2xl font-bold text-center bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500 bg-clip-text text-transparent">
            Complete Your Profile
          </h2>
          <p className="text-sm text-slate-400 text-center mt-2 mb-6 leading-relaxed">
            Welcome to Augmented Trade Tech! Please complete your account details below to finalize your registration.
          </p>

          {error && (
            <div className="p-4 mb-6 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleProfileCompleteSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Full Name *</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="First and Last name"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Phone Number (Optional)</label>
              <input
                type="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1 (555) 019-2834"
                className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
              />
            </div>

            {isPassRequired && (
              <>
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Set Password *</label>
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Confirm Password *</label>
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-type password"
                    className="w-full px-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition text-sm"
                  />
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.99] text-white font-semibold text-sm rounded-xl cursor-pointer shadow-lg shadow-indigo-600/20 transition flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Finalizing Account...
                </>
              ) : (
                "Complete Profile Setup"
              )}
            </button>
            
            <button
              type="button"
              onClick={logout}
              className="w-full text-xs text-slate-500 hover:text-slate-400 underline transition cursor-pointer text-center"
            >
              Log out & Cancel
            </button>
          </form>
        </div>
      </div>
    );
  }

  // Active user Dashboard
  const activeStatus = user?.tech_profile?.availability_status || "offline";

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      
      {/* Availability Status Bar for Technicians */}
      {user && user.is_active && user.role === "tech" && (
        <div className="bg-slate-900/60 backdrop-blur-md border-b border-slate-900 px-6 py-3 flex justify-between items-center text-slate-200">
          <div className="flex items-center gap-3">
            <div className={`w-2.5 h-2.5 rounded-full shadow-lg ${
              activeStatus === "available" ? "bg-emerald-500 shadow-emerald-500/50" :
              activeStatus === "on_job" ? "bg-blue-500 shadow-blue-500/50" :
              activeStatus === "driving" ? "bg-sky-400 shadow-sky-400/50" :
              activeStatus === "break" ? "bg-amber-500 shadow-amber-500/50" :
              activeStatus === "off_duty" ? "bg-red-500 shadow-red-500/50" :
              "bg-slate-500 shadow-slate-500/50"
            }`} />
            <span className="font-semibold text-sm capitalize">
              {activeStatus.replace("_", " ")}
            </span>
            {elapsedText && (
              <span className="text-xs text-slate-500">
                for {elapsedText}
              </span>
            )}
          </div>
          <button
            onClick={() => setIsAvailabilitySheetOpen(true)}
            className="px-3.5 py-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 rounded-lg text-indigo-300 text-xs font-semibold cursor-pointer transition"
          >
            Change Status
          </button>
        </div>
      )}

      {/* Main Header */}
      <header className="sticky top-0 z-40 w-full glass-card border-b border-white/5 px-8 py-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="Profile Avatar" className="w-9 h-9 rounded-full object-cover border border-white/10" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-bold text-sm">
              {user?.full_name?.[0] || user?.email?.[0]?.toUpperCase()}
            </div>
          )}
          <span className="font-bold text-lg bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500 bg-clip-text text-transparent tracking-tight">
            Augmented Trade Tech
          </span>
        </div>
        <button 
          onClick={logout} 
          className="px-4 py-2 bg-slate-900/60 hover:bg-red-500/10 text-slate-300 hover:text-red-400 border border-white/5 hover:border-red-500/20 text-xs font-semibold rounded-xl transition-all duration-200 flex items-center gap-1.5 cursor-pointer shadow-md"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign Out
        </button>
      </header>

      {/* Main Area */}
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-10 flex flex-col gap-8">
        
        {/* Welcome Card */}
        <div className="p-8 rounded-2xl glass-card border border-white/5 shadow-2xl relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/10 rounded-full blur-3xl -z-10 pointer-events-none" />
          <div className="space-y-3">
            <div>
              <span className={`inline-flex px-3 py-1 rounded-full text-[10px] font-bold tracking-wider uppercase border ${
                user?.role === "company_admin" ? "bg-purple-500/10 border-purple-500/20 text-purple-300" :
                user?.role === "dispatcher" ? "bg-blue-500/10 border-blue-500/20 text-blue-300" :
                "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
              }`}>
                {user?.role === "company_admin" ? "Company Admin" :
                 user?.role === "dispatcher" ? "Dispatcher" :
                 "Technician"}
              </span>
            </div>
            <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-slate-300 tracking-tight">
              Welcome back, {user?.full_name || user?.email}!
            </h1>
            <p className="text-slate-400 text-sm max-w-xl leading-relaxed">
              Your active field service operational dashboard. Access tools, coordinate dispatch, and manage team members.
            </p>
          </div>
        </div>

        {/* Action Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {user?.role === "company_admin" && (
            <>
              <Link href="/settings/team" className="block group">
                <div className="h-full p-6 glass-card glass-card-hover rounded-2xl flex flex-col gap-4">
                  <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:scale-105 transition-transform duration-300">
                    <Users className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="font-bold text-white text-lg group-hover:text-indigo-400 transition-colors flex items-center gap-1">
                      Team Management
                      <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      Invite new team members, manage access privileges, configure technician trades, and update rosters.
                    </p>
                  </div>
                </div>
              </Link>

              <Link href="/settings/integrations" className="block group">
                <div className="h-full p-6 glass-card glass-card-hover rounded-2xl flex flex-col gap-4">
                  <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 group-hover:scale-105 transition-transform duration-300">
                    <Database className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="font-bold text-white text-lg group-hover:text-purple-400 transition-colors flex items-center gap-1">
                      QuickBooks Integration
                      <ChevronRight className="w-4 h-4 opacity-0 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      Connect your QuickBooks Online account, configure service/parts mappings, and view background sync logs.
                    </p>
                  </div>
                </div>
              </Link>
            </>
          )}

          {/* Profile Card */}
          <div className="p-6 glass-card rounded-2xl flex flex-col gap-5 relative overflow-hidden">
            <div className="absolute top-0 right-0 w-40 h-40 bg-emerald-500/5 rounded-full blur-2xl pointer-events-none" />
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <User className="w-6 h-6" />
              </div>
              <h3 className="font-bold text-white text-lg">
                Profile Information
              </h3>
            </div>
            <div className="divide-y divide-white/5">
              <div className="py-3 flex justify-between text-sm items-center">
                <span className="text-slate-400">Email Address</span>
                <span className="font-medium text-slate-200">{user?.email}</span>
              </div>
              <div className="py-3 flex justify-between text-sm items-center">
                <span className="text-slate-400">Phone Number</span>
                <span className="font-medium text-slate-200">{user?.phone || "None specified"}</span>
              </div>
              <div className="py-3 flex justify-between text-sm items-center">
                <span className="text-slate-400">Account Status</span>
                <span className="font-medium text-emerald-400 flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-glow shadow-emerald-500/50" />
                  Active
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* One-Tap Availability Status Switcher Bottom Sheet / Modal */}
      {isAvailabilitySheetOpen && (
        <div 
          className="fixed inset-0 bg-black/60 z-50 flex items-end justify-center"
          onClick={() => setIsAvailabilitySheetOpen(false)}
        >
          <div 
            className="w-full max-w-lg bg-slate-950 border-t border-slate-800 rounded-t-2xl p-6 shadow-2xl flex flex-col gap-4 animate-[slideUp_0.2s_ease-out]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center">
              <h3 className="font-bold text-lg text-white">Set Availability Status</h3>
              <button
                onClick={() => setIsAvailabilitySheetOpen(false)}
                className="w-8 h-8 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 flex items-center justify-center text-slate-400 hover:text-white cursor-pointer transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Updates your status in dispatch systems immediately.
            </p>
            <div className="grid grid-cols-2 gap-3 mt-2">
              {[
                { val: "available", color: "bg-emerald-500", label: "Available", desc: "Ready for work orders" },
                { val: "on_job", color: "bg-blue-500", label: "On Job", desc: "Actively working on site" },
                { val: "driving", color: "bg-sky-400", label: "Driving", desc: "In transit to site" },
                { val: "break", color: "bg-amber-500", label: "Break", desc: "Short pause, return soon" },
                { val: "off_duty", color: "bg-red-500", label: "Off Duty", desc: "Not working today" },
                { val: "offline", color: "bg-slate-500", label: "Offline", desc: "Deactivate tracking" },
              ].map((st) => (
                <div
                  key={st.val}
                  onClick={() => handleUpdateAvailability(st.val)}
                  className={`p-3 rounded-xl border text-left cursor-pointer transition-all flex flex-col gap-1.5 ${
                    activeStatus === st.val 
                      ? "bg-indigo-500/10 border-indigo-500" 
                      : "bg-slate-900/30 border-slate-900 hover:border-slate-800"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${st.color}`} />
                    <span className="font-bold text-xs text-white">{st.label}</span>
                  </div>
                  <span className="text-[10px] text-slate-500">{st.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
