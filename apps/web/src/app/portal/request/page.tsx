"use client";

import React, { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { 
  Wrench, 
  HelpCircle, 
  Upload, 
  Image as ImageIcon, 
  X, 
  Loader2, 
  CheckCircle2, 
  AlertCircle 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Equipment {
  id: string;
  trade: string;
  equipment_type: string;
  make: string;
  model: string;
  serial_number: string;
}

export default function PortalRequestPage() {
  const { accessToken } = usePortalAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // URL defaults
  const defaultTrade = searchParams.get("trade") || "hvac";
  const defaultEqId = searchParams.get("equipment_id") || "";

  // State
  const [equipmentList, setEquipmentList] = useState<Equipment[]>([]);
  const [loadingEq, setLoadingEq] = useState(true);
  const [trade, setTrade] = useState(defaultTrade);
  const [equipmentId, setEquipmentId] = useState(defaultEqId);
  const [problem, setProblem] = useState("");
  const [priority, setPriority] = useState("routine");
  
  // Photo states
  const [selectedPhotos, setSelectedPhotos] = useState<File[]>([]);
  const [photoPreviews, setPhotoPreviews] = useState<string[]>([]);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);

  // Submission state
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch equipment list to let customer select a specific unit
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
        console.error("Failed to load equipment", err);
      } finally {
        setLoadingEq(false);
      }
    };

    fetchEquipment();
  }, [accessToken]);

  // Adjust selected equipment if trade changes
  useEffect(() => {
    // If the currently selected equipment doesn't match the active trade, clear it
    if (equipmentId) {
      const selected = equipmentList.find(e => e.id === equipmentId);
      if (selected && selected.trade !== trade) {
        setEquipmentId("");
      }
    }
  }, [trade, equipmentList, equipmentId]);

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const files = Array.from(e.target.files);
    
    setSelectedPhotos(prev => [...prev, ...files]);
    
    // Create previews
    const newPreviews = files.map(file => URL.createObjectURL(file));
    setPhotoPreviews(prev => [...prev, ...newPreviews]);
  };

  const handleRemovePhoto = (index: number) => {
    setSelectedPhotos(prev => prev.filter((_, i) => i !== index));
    
    // Revoke preview URL memory leak prevention
    URL.revokeObjectURL(photoPreviews[index]);
    setPhotoPreviews(prev => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!trade || !problem.trim()) return;

    setSubmitting(true);
    setError(null);

    try {
      const headers = { 
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}` 
      };

      // 1. Create the Service Request (Job)
      const res = await fetch(`${API_URL}/portal/requests`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          trade,
          reported_problem: problem.trim(),
          equipment_id: equipmentId || null,
          priority
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create service request");
      }

      const job = await res.json();
      const jobId = job.id;

      // 2. Upload and Register Photos if any were selected
      if (selectedPhotos.length > 0) {
        setUploadingPhotos(true);
        for (const file of selectedPhotos) {
          // A. Get Presigned S3 URL
          const presignRes = await fetch(`${API_URL}/portal/requests/${jobId}/photos/presign`, {
            method: "POST",
            headers,
            body: JSON.stringify({ photo_type: "general" })
          });

          if (!presignRes.ok) continue; // Skip failed signature
          const { upload_url, s3_key, headers: uploadHeaders } = await presignRes.json();

          // B. PUT to upload url
          await new Promise<void>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("PUT", upload_url, true);
            if (uploadHeaders) {
              Object.entries(uploadHeaders).forEach(([k, v]) => {
                xhr.setRequestHeader(k, v as string);
              });
            }
            xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject());
            xhr.onerror = () => reject();
            xhr.send(file);
          });

          // C. Register photo metadata
          const cdn_url = upload_url.split("?")[0];
          await fetch(`${API_URL}/portal/requests/${jobId}/photos`, {
            method: "POST",
            headers,
            body: JSON.stringify({
              photo_type: "general",
              s3_key,
              cdn_url,
              caption: "Uploaded by customer during service request",
              file_size_bytes: file.size,
              mime_type: file.type || "image/jpeg"
            })
          });
        }
      }

      // Success
      setSubmitSuccess(job);
    } catch (err: any) {
      console.error("Failed to submit service request", err);
      setError(err.message || "An unexpected error occurred. Please try again.");
    } finally {
      setSubmitting(false);
      setUploadingPhotos(false);
    }
  };

  const filteredEquipment = equipmentList.filter(eq => eq.trade === trade);

  if (submitSuccess) {
    return (
      <div className="flex items-center justify-center min-h-[60vh] px-4 animate-fade-in">
        <div className="w-full max-w-md p-8 rounded-2xl glass-card border border-white/5 shadow-2xl text-center space-y-6">
          <div className="h-16 w-16 bg-emerald-500/10 rounded-full flex items-center justify-center text-emerald-400 mx-auto">
            <CheckCircle2 className="h-10 w-10" />
          </div>
          <div className="space-y-2">
            <h3 className="text-2xl font-bold text-white">Request Confirmed!</h3>
            <p className="text-slate-400 text-sm">
              Your service request has been received. A technician will review your request and schedule a visit.
            </p>
          </div>

          <div className="p-4 rounded-xl bg-white/[0.02] border border-white/5 text-sm divide-y divide-white/5">
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Request Number:</span>
              <span className="font-bold text-white">{submitSuccess.job_number}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Trade:</span>
              <span className="font-semibold text-white capitalize">{submitSuccess.trade.replace("_", " ")}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-slate-400">Status:</span>
              <span className="font-bold text-amber-400 capitalize">{submitSuccess.status}</span>
            </div>
          </div>

          <button
            onClick={() => router.push("/portal/home")}
            className="w-full py-3 rounded-xl hover:opacity-95 transition-all text-white font-semibold text-sm cursor-pointer"
            style={{ backgroundColor: "var(--primary-color)" }}
          >
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Request Service</h1>
        <p className="text-slate-400 text-sm">Fill out the details below to schedule repair or maintenance service.</p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/25 flex items-center gap-3 text-red-400 text-sm">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 p-6 rounded-2xl glass-card border border-white/5">
        
        {/* Trade Selector */}
        <div className="space-y-3">
          <label className="text-sm font-semibold text-slate-300 block">Select Service Category</label>
          <div className="grid grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setTrade("hvac")}
              className={`p-4 rounded-xl border text-center transition-all flex flex-col items-center gap-2 cursor-pointer ${
                trade === "hvac"
                  ? "border-[var(--primary-color)] bg-[var(--primary-color)]/5 text-white"
                  : "border-white/5 bg-white/[0.005] text-slate-400 hover:text-white"
              }`}
            >
              <Wrench className="h-6 w-6" />
              <span className="text-sm font-bold">HVAC / Climate</span>
            </button>
            <button
              type="button"
              onClick={() => setTrade("garage_door")}
              className={`p-4 rounded-xl border text-center transition-all flex flex-col items-center gap-2 cursor-pointer ${
                trade === "garage_door"
                  ? "border-[var(--primary-color)] bg-[var(--primary-color)]/5 text-white"
                  : "border-white/5 bg-white/[0.005] text-slate-400 hover:text-white"
              }`}
            >
              <HelpCircle className="h-6 w-6" />
              <span className="text-sm font-bold">Garage Doors</span>
            </button>
          </div>
        </div>

        {/* Equipment Selector */}
        <div className="space-y-2">
          <label htmlFor="equipment" className="text-sm font-semibold text-slate-300 block">
            Select Unit (Optional)
          </label>
          {loadingEq ? (
            <Loader2 className="h-4 w-4 animate-spin text-[var(--primary-color)]" />
          ) : (
            <select
              id="equipment"
              value={equipmentId}
              onChange={(e) => setEquipmentId(e.target.value)}
              className="w-full p-3 rounded-xl glass-input text-slate-300 focus:outline-none text-sm bg-gray-900 border border-white/5 cursor-pointer"
            >
              <option value="">-- No specific unit / Other --</option>
              {filteredEquipment.map(eq => (
                <option key={eq.id} value={eq.id}>
                  {eq.make} {eq.equipment_type} (S/N: {eq.serial_number})
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Problem Description */}
        <div className="space-y-2">
          <label htmlFor="problem" className="text-sm font-semibold text-slate-300 block">
            Problem Description
          </label>
          <textarea
            id="problem"
            required
            rows={4}
            value={problem}
            onChange={(e) => setProblem(e.target.value)}
            placeholder="Please detail what is wrong. Example: AC blower is making a loud squealing sound, or Garage Door springs feel loose..."
            className="w-full p-4 rounded-xl glass-input text-slate-200 placeholder-slate-500 focus:outline-none text-sm leading-relaxed"
            disabled={submitting}
          />
        </div>

        {/* Priority Selector */}
        <div className="space-y-2">
          <label htmlFor="priority" className="text-sm font-semibold text-slate-300 block">
            Priority Level
          </label>
          <select
            id="priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full p-3 rounded-xl glass-input text-slate-350 focus:outline-none text-sm bg-gray-900 border border-white/5 cursor-pointer"
          >
            <option value="routine">Routine - Standard Maintenance/Repair</option>
            <option value="urgent">Urgent - High Climate Discomfort / Trap Risk</option>
            <option value="emergency">Emergency - Threat to Property or Safety</option>
          </select>
        </div>

        {/* Photos Attachment */}
        <div className="space-y-3">
          <label className="text-sm font-semibold text-slate-300 block">Attach Photos (Optional)</label>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-4">
            
            {/* Upload Button */}
            <label className="border border-dashed border-white/10 hover:border-white/20 bg-white/[0.005] hover:bg-white/[0.015] rounded-xl flex flex-col items-center justify-center cursor-pointer aspect-square p-2 group transition-all">
              <Upload className="h-5 w-5 text-slate-550 group-hover:text-white transition-colors" />
              <span className="text-[10px] text-slate-550 font-bold mt-1 text-center">Add Photo</span>
              <input 
                type="file" 
                multiple 
                accept="image/*" 
                onChange={handlePhotoSelect} 
                className="hidden" 
                disabled={submitting}
              />
            </label>

            {/* Previews */}
            {photoPreviews.map((preview, index) => (
              <div key={index} className="relative rounded-xl overflow-hidden border border-white/5 aspect-square">
                <img 
                  src={preview} 
                  alt={`Preview ${index}`} 
                  className="w-full h-full object-cover" 
                />
                <button
                  type="button"
                  onClick={() => handleRemovePhoto(index)}
                  className="absolute top-1 right-1 p-1 bg-black/70 hover:bg-black text-white hover:text-red-400 rounded-full transition-all cursor-pointer"
                  disabled={submitting}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}

          </div>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={submitting}
          className="w-full py-3.5 rounded-xl hover:opacity-95 active:scale-[0.99] text-white font-bold text-sm transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          style={{ backgroundColor: "var(--primary-color)" }}
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              {uploadingPhotos ? "Uploading Photos..." : "Submitting Service Request..."}
            </>
          ) : (
            "Submit Request"
          )}
        </button>

      </form>
    </div>
  );
}
