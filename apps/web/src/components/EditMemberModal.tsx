"use client";

import React, { useState, useEffect } from "react";
import { useAuth } from "../hooks/useAuth";
import { X, Loader2, User, Phone, Users, ShieldAlert, Award, FileText, Truck, Calendar } from "lucide-react";

interface EditMemberModalProps {
  isOpen: boolean;
  member: any; // User object containing tech_profile
  onClose: () => void;
  onSuccess: () => void;
}

export function EditMemberModal({ isOpen, member, onClose, onSuccess }: EditMemberModalProps) {
  const { accessToken } = useAuth();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [role, setRole] = useState("tech");

  // Tech Profile fields
  const [trades, setTrades] = useState<string[]>([]);
  const [certifications, setCertifications] = useState("");
  const [skills, setSkills] = useState("");
  const [truckId, setTruckId] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [hireDate, setHireDate] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate state when member changes or modal opens
  useEffect(() => {
    if (member) {
      setFullName(member.full_name || "");
      setPhone(member.phone || "");
      setRole(member.role || "tech");

      if (member.tech_profile) {
        const tp = member.tech_profile;
        setTrades(tp.trades || []);

        // Certs are array of dicts e.g. [{"name": "EPA 608"}]
        const certNames = (tp.certifications || [])
          .map((c: any) => c.name || c)
          .join(", ");
        setCertifications(certNames);

        setSkills((tp.skills || []).join(", "));
        setTruckId(tp.truck_id || "");
        setLicenseNumber(tp.license_number || "");
        setHireDate(tp.hire_date || "");
      } else {
        setTrades([]);
        setCertifications("");
        setSkills("");
        setTruckId("");
        setLicenseNumber("");
        setHireDate("");
      }
    }
  }, [member, isOpen]);

  if (!isOpen || !member) return null;

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

    // Map certs text to objects e.g. [{"name": "EPA"}]
    const certArray = certifications
      .split(",")
      .map((c) => c.trim())
      .filter((c) => c.length > 0)
      .map((name) => ({ name }));

    // Map skills text to array of strings
    const skillArray = skills
      .split(",")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    try {
      const res = await fetch(`${API_URL}/users/${member.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          full_name: fullName || undefined,
          phone: phone || undefined,
          role,
          trades: role === "tech" ? trades : undefined,
          certifications: role === "tech" ? certArray : undefined,
          skills: role === "tech" ? skillArray : undefined,
          truck_id: role === "tech" ? truckId || null : undefined,
          license_number: role === "tech" ? licenseNumber || null : undefined,
          hire_date: role === "tech" ? hireDate || null : undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to update profile");
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
        className="w-full max-w-md bg-slate-900/40 backdrop-blur-md border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center mb-5 flex-shrink-0">
          <h2 className="text-xl font-bold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
            Edit Team Member
          </h2>
          <button 
            onClick={onClose} 
            className="w-8 h-8 rounded-lg bg-slate-800/40 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 flex items-center justify-center text-slate-400 hover:text-white cursor-pointer transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {error && (
          <div className="p-3 mb-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs flex-shrink-0">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col overflow-hidden">
          <div className="flex-1 overflow-y-auto space-y-4 pr-1.5 mb-6 scrollbar-thin scrollbar-thumb-slate-850 scrollbar-track-transparent">
            
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Full Name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Full Name"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Phone Number</label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  type="text"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+1 (555) 019-2834"
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                  disabled={isSubmitting}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Role</label>
              <div className="relative">
                <Users className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm appearance-none cursor-pointer"
                  disabled={isSubmitting}
                >
                  <option value="tech">Technician</option>
                  <option value="dispatcher">Dispatcher</option>
                  <option value="company_admin">Admin</option>
                </select>
              </div>
            </div>

            {role === "tech" && (
              <>
                <div className="text-xs font-bold tracking-wider uppercase text-indigo-400 pt-3 border-t border-slate-900">
                  Technician Profile Details
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Trades Managed</label>
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

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    Certifications (comma separated)
                  </label>
                  <div className="relative">
                    <Award className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={certifications}
                      onChange={(e) => setCertifications(e.target.value)}
                      placeholder="EPA 608, NATE, OSHA-10"
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
                    Skills (comma separated)
                  </label>
                  <div className="relative">
                    <FileText className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={skills}
                      onChange={(e) => setSkills(e.target.value)}
                      placeholder="AC Repair, Wiring, Gas Furnaces"
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Truck ID</label>
                  <div className="relative">
                    <Truck className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={truckId}
                      onChange={(e) => setTruckId(e.target.value)}
                      placeholder="TRUCK-401"
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">License Number</label>
                  <div className="relative">
                    <Award className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="text"
                      value={licenseNumber}
                      onChange={(e) => setLicenseNumber(e.target.value)}
                      placeholder="LIC-928374"
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">Hire Date</label>
                  <div className="relative">
                    <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                    <input
                      type="date"
                      value={hireDate}
                      onChange={(e) => setHireDate(e.target.value)}
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition text-sm cursor-pointer"
                      disabled={isSubmitting}
                    />
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="flex justify-end gap-3 flex-shrink-0 pt-4 border-t border-slate-900/60">
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
                  Saving...
                </>
              ) : (
                "Save Changes"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
