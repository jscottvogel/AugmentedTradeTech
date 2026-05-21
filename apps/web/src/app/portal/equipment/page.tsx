"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { 
  Cpu, 
  Calendar, 
  FileText, 
  Wrench, 
  Info, 
  ChevronDown, 
  ChevronUp, 
  Copy, 
  Check, 
  Loader2 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ServiceJob {
  id: string;
  job_number: string;
  job_type: string;
  completed_at: string;
}

interface Equipment {
  id: string;
  trade: string;
  equipment_type: string;
  make: string;
  model: string;
  serial_number: string;
  install_date: string | null;
  warranty_expires: string | null;
  location_notes: string | null;
  nameplate_photo_url: string | null;
  is_primary: boolean;
  service_history: ServiceJob[];
}

export default function PortalEquipmentPage() {
  const { accessToken } = usePortalAuth();
  const router = useRouter();

  const [equipmentList, setEquipmentList] = useState<Equipment[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedUnitId, setExpandedUnitId] = useState<string | null>(null);
  const [copiedSerial, setCopiedSerial] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;

    const fetchEquipment = async () => {
      try {
        const res = await fetch(`${API_URL}/portal/equipment`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const data = await res.json();
          setEquipmentList(data);
        }
      } catch (err) {
        console.error("Failed to fetch equipment list", err);
      } finally {
        setLoading(false);
      }
    };

    fetchEquipment();
  }, [accessToken]);

  const handleCopySerial = (serial: string) => {
    navigator.clipboard.writeText(serial);
    setCopiedSerial(serial);
    setTimeout(() => setCopiedSerial(null), 2000);
  };

  const toggleExpand = (id: string) => {
    setExpandedUnitId(expandedUnitId === id ? null : id);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Your Equipment</h1>
        <p className="text-slate-400 text-sm">Monitor your service schedules, warranties, and unit details.</p>
      </div>

      {equipmentList.length === 0 ? (
        <div className="p-12 rounded-2xl glass-card border border-white/5 text-center text-slate-500">
          No registered equipment found.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {equipmentList.map(eq => (
            <div key={eq.id} className="rounded-2xl glass-card border border-white/5 overflow-hidden flex flex-col justify-between">
              
              {/* Card Header */}
              <div className="p-6 border-b border-white/5 flex items-start justify-between">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {eq.trade.replace("_", " ")}
                    </span>
                    {eq.is_primary && (
                      <span className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded bg-[var(--primary-color)]/10 text-[var(--primary-color)]">
                        Primary
                      </span>
                    )}
                  </div>
                  <h3 className="text-lg font-bold text-white capitalize">
                    {eq.make} {eq.equipment_type}
                  </h3>
                  <p className="text-xs text-slate-400">Model: {eq.model}</p>
                </div>
                <div className="h-10 w-10 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-center text-[var(--primary-color)]">
                  <Cpu className="h-5 w-5" />
                </div>
              </div>

              {/* Card Body */}
              <div className="p-6 space-y-4 flex-grow text-sm">
                
                {/* Image or Placeholder */}
                {eq.nameplate_photo_url ? (
                  <div className="relative rounded-xl overflow-hidden h-32 border border-white/5 group">
                    <img 
                      src={eq.nameplate_photo_url} 
                      alt="Unit nameplate info" 
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-white/10 h-16 flex items-center justify-center text-xs text-slate-500 bg-white/[0.005]">
                    No photo attached
                  </div>
                )}

                {/* Details Grid */}
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="text-slate-550 block">Serial Number</span>
                    <div className="flex items-center gap-1.5 mt-0.5 font-mono text-white text-[13px]">
                      <span className="truncate max-w-[120px]">{eq.serial_number}</span>
                      <button 
                        onClick={() => handleCopySerial(eq.serial_number)}
                        className="text-slate-500 hover:text-white cursor-pointer"
                        title="Copy Serial Number"
                      >
                        {copiedSerial === eq.serial_number ? (
                          <Check className="h-3.5 w-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div>
                    <span className="text-slate-555 block">Install Date</span>
                    <span className="font-semibold text-white mt-0.5 block">
                      {eq.install_date ? new Date(eq.install_date).toLocaleDateString() : "N/A"}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-555 block">Warranty Expire</span>
                    <span className={`font-semibold mt-0.5 block ${
                      eq.warranty_expires && new Date(eq.warranty_expires) < new Date() 
                        ? "text-red-400" 
                        : "text-white"
                    }`}>
                      {eq.warranty_expires ? new Date(eq.warranty_expires).toLocaleDateString() : "N/A"}
                    </span>
                  </div>
                </div>

                {/* Location Notes */}
                {eq.location_notes && (
                  <div className="p-3 rounded-lg border border-white/5 bg-white/[0.005] flex gap-2">
                    <Info className="h-4 w-4 text-[var(--primary-color)] shrink-0 mt-0.5" />
                    <div>
                      <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Location Notes</span>
                      <p className="text-xs text-slate-300 mt-0.5">{eq.location_notes}</p>
                    </div>
                  </div>
                )}

                {/* Service History Accordion */}
                <div className="border border-white/5 rounded-xl overflow-hidden bg-white/[0.005]">
                  <button
                    onClick={() => toggleExpand(eq.id)}
                    className="w-full p-4 flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-white transition-all cursor-pointer"
                  >
                    <span className="flex items-center gap-1.5">
                      <Wrench className="h-3.5 w-3.5 text-[var(--primary-color)]" />
                      Unit Service History ({eq.service_history.length})
                    </span>
                    {expandedUnitId === eq.id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </button>

                  {expandedUnitId === eq.id && (
                    <div className="px-4 pb-4 border-t border-white/5 divide-y divide-white/5">
                      {eq.service_history.length === 0 ? (
                        <p className="text-xs text-slate-500 pt-3 italic">No past jobs registered for this unit.</p>
                      ) : (
                        eq.service_history.map(sh => (
                          <div key={sh.id} className="py-2.5 flex items-center justify-between text-xs">
                            <div>
                              <p className="font-semibold text-white">{sh.job_number}</p>
                              <p className="text-[10px] text-slate-500 capitalize">{sh.job_type} Service</p>
                            </div>
                            <span className="text-[10px] text-slate-400 font-medium">
                              {new Date(sh.completed_at).toLocaleDateString()}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </div>

              </div>

              {/* Card Footer Actions */}
              <div className="p-4 border-t border-white/5 bg-white/[0.008] flex justify-end">
                <button
                  onClick={() => router.push(`/portal/request?equipment_id=${eq.id}&trade=${eq.trade}`)}
                  className="px-4 py-2 rounded-lg border border-white/5 hover:border-[var(--primary-color)]/30 text-xs font-bold text-slate-300 hover:text-[var(--primary-color)] transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Wrench className="h-3 w-3" />
                  Request Service
                </button>
              </div>

            </div>
          ))}
        </div>
      )}
    </div>
  );
}
