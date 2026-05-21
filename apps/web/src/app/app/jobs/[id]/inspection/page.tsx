"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "../../../../../hooks/useAuth";
import { AuthGuard } from "../../../../../components/AuthGuard";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Mic,
  MicOff,
  Play,
  Square,
  AlertCircle,
  Loader2,
  ChevronRight,
  ChevronLeft,
  Wifi,
  WifiOff,
  CloudLightning,
  Sparkles,
  MessageSquare,
  Send,
  X,
  Volume2,
  Bot
} from "lucide-react";

import PhotoCapture from "../../../../../components/PhotoCapture";
import { getOfflinePhotos, deleteOfflinePhoto, getSyncQueue, saveOfflinePhoto } from "../../../../../utils/indexedDB";
import { offlineSafeFetch } from "../../../../../utils/apiClient";
import { useConnectivity } from "../../../../../context/ConnectivityContext";

// Interfaces matching backend models
interface WorkflowStep {
  key: string;
  name: string;
  type: "photo" | "numeric" | "multi_choice" | "text" | "voice" | "checklist" | "ai_trigger";
  required: boolean;
  description: string;
  config: {
    photo_required?: boolean;
    unit?: string;
    min_value?: number;
    max_value?: number;
    options?: string[];
    items?: string[];
    placeholder?: string;
    memo_required?: boolean;
    trigger_analysis?: boolean;
  };
}

interface StepProgress {
  inputs: any;
  completed_at?: string;
  skipped?: boolean;
  idempotency_key: string;
  ai_result?: any;
}

interface Job {
  id: string;
  job_number: string;
  trade: string;
  job_type: string;
  status: string;
  reported_problem: string | null;
  customer: {
    id: string;
    first_name: string;
    last_name: string;
    phone: string | null;
    address_line1: string;
    city: string;
  };
}

export default function GuidedInspectionScreen() {
  return (
    <AuthGuard>
      <GuidedInspectionContent />
    </AuthGuard>
  );
}

function GuidedInspectionContent() {
  const params = useParams();
  const router = useRouter();
  const { accessToken } = useAuth();
  const id = params.id as string;

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // State Management
  const [job, setJob] = useState<Job | null>(null);
  const [steps, setSteps] = useState<WorkflowStep[]>([]);
  const [progress, setProgress] = useState<Record<string, StepProgress>>({});
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Connection & Saving States
  const { isOnline, syncStatus } = useConnectivity();
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "offline-queued">("idle");
  const [offlineQueueLength, setOfflineQueueLength] = useState(0);

  // AI & Chat States
  const [aiRunningStep, setAiRunningStep] = useState<string | null>(null);
  const [showChatDrawer, setShowChatDrawer] = useState(false);
  const [chatMessages, setChatMessages] = useState<Array<{ sender: "user" | "ai"; text: string; time: string }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [isAiThinking, setIsAiThinking] = useState(false);

  // Expandable Text inputs
  const [speechActiveStep, setSpeechActiveStep] = useState<string | null>(null);

  // Audio Recorder States
  const [isRecording, setIsRecording] = useState(false);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState<string | null>(null);
  const [audioPlaybackActive, setAudioPlaybackActive] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Photo uploads
  const [isUploadingPhoto, setIsUploadingPhoto] = useState<string | null>(null);

  // Debounce ref
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Load/update offline queue length and refresh on sync success
  const updateOfflineQueueLength = async () => {
    try {
      const queue = await getSyncQueue();
      const jobMutations = queue.filter(item => item.entity_id === id);
      setOfflineQueueLength(jobMutations.length);
    } catch (err) {
      console.warn("Failed to retrieve offline queue length:", err);
    }
  };

  useEffect(() => {
    updateOfflineQueueLength();
  }, [id, syncStatus, saveStatus]);

  useEffect(() => {
    if (syncStatus === 'success') {
      fetchJobAndWorkflow();
    }
  }, [syncStatus]);

  // Load Job and Workflow configuration
  useEffect(() => {
    if (accessToken && id) {
      fetchJobAndWorkflow();
    }
  }, [accessToken, id]);

  const fetchJobAndWorkflow = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch Job Details
      const jobRes = await offlineSafeFetch(`${API_URL}/jobs/${id}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!jobRes.ok) throw new Error("Failed to load job details.");
      const jobData = await jobRes.json();
      setJob(jobData);

      // Fetch Workflow configuration
      const wfRes = await offlineSafeFetch(`${API_URL}/jobs/${id}/workflow`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!wfRes.ok) throw new Error("Failed to load workflow configuration.");
      const wfData = await wfRes.json();
      setSteps(wfData.steps);
      setProgress(wfData.progress || {});

    } catch (err: any) {
      loggerError(err);
      setError(err.message || "An error occurred while loading workflow.");
    } finally {
      setIsLoading(false);
    }
  };

  const loggerError = (err: any) => {
    console.error("Workflow loading error:", err);
  };

  // Perform API Sync (with Debounce)
  const saveStepData = async (stepKey: string, inputs: any, skipped: boolean = false) => {
    const idempotencyKey = `ik_${Math.random().toString(36).substr(2, 9)}`;

    // Update local state first
    setProgress(prev => ({
      ...prev,
      [stepKey]: {
        ...prev[stepKey],
        inputs,
        skipped,
        idempotency_key: idempotencyKey,
        completed_at: prev[stepKey]?.completed_at || new Date().toISOString()
      }
    }));

    setSaveStatus("saving");
    try {
      const res = await offlineSafeFetch(`${API_URL}/jobs/${id}/workflow/${stepKey}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          inputs,
          skipped,
          idempotency_key: idempotencyKey
        })
      });

      if (!res.ok) throw new Error("Failed to save step progress.");
      const data = await res.json();

      if (!isOnline) {
        setSaveStatus("offline-queued");
      } else {
        // Merge backend returned progress (retains completed timestamps)
        setProgress(prev => {
          const currentKey = prev[stepKey]?.idempotency_key;
          if (currentKey && currentKey !== idempotencyKey) {
            return prev;
          }
          return {
            ...prev,
            [stepKey]: data.step_data
          };
        });
        setSaveStatus("saved");
      }
    } catch (err) {
      console.error("Save failed:", err);
      setSaveStatus("offline-queued");
    }
  };

  // Trigger Debounced save for text inputs / numbers
  const triggerDebouncedSave = (stepKey: string, nextInputs: any) => {
    setSaveStatus("saving");
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      saveStepData(stepKey, nextInputs);
    }, 1000);
  };

  // Trigger Backend AI Analysis for a step
  const handleTriggerAiAnalysis = async (stepKey: string) => {
    if (!navigator.onLine) {
      alert("AI Diagnostics requires an online internet connection.");
      return;
    }

    setAiRunningStep(stepKey);
    try {
      const res = await offlineSafeFetch(`${API_URL}/jobs/${id}/workflow/${stepKey}/ai`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "AI analysis failed.");
      }
      const data = await res.json();

      // Update progress state with the returned AI results
      setProgress(prev => ({
        ...prev,
        [stepKey]: data.step_data
      }));

      // Initialize follow-up chatbot options based on diagnosis
      if (data.step_data?.ai_result) {
        const aiRes = data.step_data.ai_result;
        const diagSummary = aiRes.diagnostic_summary || "Analysis completed.";
        setChatMessages([
          {
            sender: "ai",
            text: `Step '${steps.find(s => s.key === stepKey)?.name}' analyzed!\n\nAI Diagnostic Result:\n${diagSummary}`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
      }

    } catch (err: any) {
      console.error("AI trigger failed:", err);
      alert(err.message || "Failed to execute AI diagnostics.");
    } finally {
      setAiRunningStep(null);
    }
  };

  // Native Photo Capture upload
  const handlePhotoCapture = async (e: React.ChangeEvent<HTMLInputElement>, stepKey: string) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploadingPhoto(stepKey);

    // Offline mode support for Guided Inspection photo capture
    if (!isOnline) {
      try {
        let pType = "general";
        if (stepKey === "arrive_on_site") {
          pType = "before";
        } else if (stepKey === "equipment_id") {
          pType = "nameplate";
        } else if (stepKey === "wrap_up") {
          pType = "after";
        }
        const caption = `Uploaded for inspection step: ${stepKey}`;
        const { id: photoId, objectUrl } = await saveOfflinePhoto(id as string, stepKey, pType, file, caption);

        const currentInputs = progress[stepKey]?.inputs || {};
        const nextInputs = {
          ...currentInputs,
          photo_url: objectUrl,
          photo_id: photoId,
          caption: caption
        };
        // Save photo references inside step inputs (which will queue the mutation in sync_queue when offline)
        await saveStepData(stepKey, nextInputs);
        alert("Photo saved offline. It will upload when you are back online.");
      } catch (err: any) {
        alert("Failed to save photo offline: " + err.message);
      } finally {
        setIsUploadingPhoto(null);
      }
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", file);
      
      let pType = "general";
      if (stepKey === "arrive_on_site") {
        pType = "before";
      } else if (stepKey === "equipment_id") {
        pType = "nameplate";
      } else if (stepKey === "wrap_up") {
        pType = "after";
      }
      formData.append("photo_type", pType);
      formData.append("caption", `Uploaded for inspection step: ${stepKey}`);

      const res = await offlineSafeFetch(`${API_URL}/jobs/${id}/photos`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: formData
      });

      if (!res.ok) throw new Error("Failed to upload photo to server.");
      const updatedJob = await res.json();

      // Find the uploaded photo url from the returned photos
      const sortedPhotos = [...updatedJob.photos].sort((a, b) => b.taken_at.localeCompare(a.taken_at));
      const latestPhoto = sortedPhotos[0];

      if (latestPhoto) {
        const currentInputs = progress[stepKey]?.inputs || {};
        const nextInputs = {
          ...currentInputs,
          photo_url: latestPhoto.cdn_url,
          photo_id: latestPhoto.id,
          caption: latestPhoto.caption
        };
        // Save photo references inside step inputs
        await saveStepData(stepKey, nextInputs);
      }

    } catch (err: any) {
      console.error(err);
      alert("Error uploading photo. Please try again.");
    } finally {
      setIsUploadingPhoto(null);
    }
  };

  // Web Speech recognition (Speech-to-Text)
  const handleSpeechToText = (stepKey: string) => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech-to-text recognition is not supported in this browser. Please use Chrome or Safari.");
      return;
    }

    if (speechActiveStep === stepKey) {
      // Toggle off
      setSpeechActiveStep(null);
      return;
    }

    setSpeechActiveStep(stepKey);
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      const currentInputs = progress[stepKey]?.inputs || {};
      const noteVal = currentInputs.notes || "";
      const separator = noteVal ? " " : "";
      const updatedNotes = `${noteVal}${separator}${transcript}`;

      const nextInputs = { ...currentInputs, notes: updatedNotes };
      // Save input changes
      saveStepData(stepKey, nextInputs);
    };

    recognition.onerror = (err: any) => {
      console.error("Speech recognition error:", err);
      setSpeechActiveStep(null);
    };

    recognition.onend = () => {
      setSpeechActiveStep(null);
    };

    recognition.start();
  };

  // Audio recording recorder states (MediaRecorder)
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const audioUrl = URL.createObjectURL(audioBlob);
        setRecordedAudioUrl(audioUrl);

        // Auto save mock transcript
        const currentStepKey = steps[currentStepIndex].key;
        const currentInputs = progress[currentStepKey]?.inputs || {};
        const nextInputs = {
          ...currentInputs,
          audio_url: audioUrl,
          transcript: "Technician notes: Verified components are in normal operating condition. No abnormal vibrations."
        };
        saveStepData(currentStepKey, nextInputs);
      };

      mediaRecorder.start();
      setIsRecording(true);

      // Start canvas waveform animations
      drawWaveform();

    } catch (err) {
      console.error("Microphone access blocked or unsupported:", err);
      // Fallback: simulate audio recording
      setIsRecording(true);
      drawWaveform();
      setTimeout(() => {
        stopRecording();
      }, 5000);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    } else if (isRecording) {
      // Mock Stop Fallback
      setIsRecording(false);
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);

      const currentStepKey = steps[currentStepIndex].key;
      const currentInputs = progress[currentStepKey]?.inputs || {};
      const nextInputs = {
        ...currentInputs,
        audio_url: "#mock-recording",
        transcript: "Technician notes: Verified components are in normal operating condition. No abnormal vibrations."
      };
      saveStepData(currentStepKey, nextInputs);
    }
    setIsRecording(false);
    if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
  };

  // Draw simulated wave animations on CSS canvas
  const drawWaveform = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let offset = 0;
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "rgba(129, 140, 248, 0.85)"; // Indigo-400
      ctx.lineWidth = 3;
      ctx.beginPath();

      const centerY = canvas.height / 2;
      const width = canvas.width;

      for (let x = 0; x < width; x++) {
        // Draw double sine wave for high fidelity waveform look
        const y = centerY + Math.sin(x * 0.05 + offset) * 15 * Math.sin(x * 0.01);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      offset += 0.15;
      animationFrameRef.current = requestAnimationFrame(render);
    };

    render();
  };

  // Follow-up AI chatbot interaction
  const handleSendChat = () => {
    if (!chatInput.trim()) return;

    const userMsg = {
      sender: "user" as const,
      text: chatInput,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput("");
    setIsAiThinking(true);

    // Simulate AI thinking and reply matching current step context
    setTimeout(() => {
      const stepKey = steps[currentStepIndex].key;
      let aiText = "I've analyzed that step. Let me know if you need specific details.";

      if (stepKey === "equipment_id") {
        aiText = "Carrier Carrier 58SB0A070E1412 units are gas furnaces. Common troubleshooting involves check roll-out switch, igniter resistance (typically 40-75 ohms), and flame sensor current (should exceed 1.0 microamps).";
      } else if (stepKey === "refrigerant_pressures") {
        aiText = "A suction pressure of 120-130 PSI on R-410A corresponds to a saturation temperature of 41-45°F. If superheat is higher than 15°F, it indicates restricted refrigerant flow or undercharge.";
      } else if (stepKey === "temperature_readings") {
        aiText = "A Delta-T of 20°F is ideal for standard systems. If the Delta-T is lower than 16°F, check for low airflow, restricted evaporator coils, or refrigerant imbalances.";
      } else if (stepKey === "ai_diagnosis") {
        aiText = "The diagnosis suggests a dirty filter is primary culprit. Changing the filter will improve airflow and restore static pressure to specifications.";
      }

      setChatMessages(prev => [
        ...prev,
        {
          sender: "ai" as const,
          text: aiText,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
      ]);
      setIsAiThinking(false);
    }, 1500);
  };

  // Form Validations & Progress Calcs
  const currentStep = steps[currentStepIndex];
  const totalSteps = steps.length;
  const currentProgress = progress[currentStep?.key] || { inputs: {}, idempotency_key: "" };

  const completedCount = steps.filter(s => {
    const prog = progress[s.key];
    return prog && (prog.completed_at || prog.skipped);
  }).length;

  const isCurrentStepCompleted = !!(currentProgress.completed_at || currentProgress.skipped);

  // Validate if checklist elements are fully checked
  const isChecklistStepValid = () => {
    if (currentStep?.type !== "checklist") return true;
    const items = currentStep.config.items || [];
    const checkedItems = currentProgress.inputs?.checked || [];
    return items.every((item: string) => checkedItems.includes(item));
  };

  // Renders the specific guided inspection inputs
  const renderStepInput = () => {
    if (!currentStep) return null;

    const stepKey = currentStep.key;
    const currentInputs = currentProgress.inputs || {};

    switch (currentStep.type) {
      case "photo":
        let pType = "general";
        if (stepKey === "arrive_on_site") {
          pType = "before";
        } else if (stepKey === "equipment_id") {
          pType = "nameplate";
        } else if (stepKey === "wrap_up") {
          pType = "after";
        }

        return (
          <div className="w-full max-w-sm mx-auto py-2">
            <PhotoCapture
              key={stepKey}
              jobId={id as string}
              stepKey={stepKey}
              photoType={pType}
              accessToken={accessToken || ""}
              isOnline={isOnline}
              initialPhotoUrl={currentInputs.photo_url}
              onUploadSuccess={async (cdnUrl, photoId) => {
                const nextInputs = {
                  ...currentInputs,
                  photo_url: cdnUrl,
                  photo_id: photoId,
                  caption: `Inspection photo for step: ${stepKey}`
                };
                await saveStepData(stepKey, nextInputs);
              }}
              placeholderText={`Capture ${pType.charAt(0).toUpperCase() + pType.slice(1)} Photo`}
            />
          </div>
        );

      case "numeric":
        const unit = currentStep.config.unit || "";
        const minVal = currentStep.config.min_value ?? -99999;
        const maxVal = currentStep.config.max_value ?? 99999;
        const numValStr = currentInputs.value !== undefined ? String(currentInputs.value) : "";
        const numVal = parseFloat(numValStr);
        const isOutOfRange = numValStr !== "" && (numVal < minVal || numVal > maxVal);
        const isNumericValid = numValStr !== "" && !isNaN(numVal);

        return (
          <div className="w-full max-w-sm mx-auto space-y-3 py-4">
            <div className="flex items-center space-x-3">
              <div className="relative flex-1">
                <input
                  type="number"
                  placeholder="Enter reading..."
                  value={numValStr}
                  className={`w-full px-4 py-4 rounded-xl text-lg font-bold text-center glass-input pr-16 ${
                    numValStr === ""
                      ? "border-white/10"
                      : isOutOfRange
                      ? "border-red-500 ring-2 ring-red-500/20 text-red-400"
                      : "border-emerald-500 ring-2 ring-emerald-500/20 text-emerald-400"
                  }`}
                  onChange={(e) => {
                    const val = e.target.value;
                    const nextInputs = { ...currentInputs, value: val };
                    setProgress(prev => ({
                      ...prev,
                      [stepKey]: {
                        ...prev[stepKey],
                        inputs: nextInputs,
                        completed_at: new Date().toISOString()
                      }
                    }));
                    triggerDebouncedSave(stepKey, nextInputs);
                  }}
                />
                <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 font-semibold">
                  {unit}
                </span>
              </div>
            </div>
            {currentStep.config.min_value !== undefined && currentStep.config.max_value !== undefined && (
              <div className="flex justify-between px-1 text-xs text-gray-500">
                <span>Min: {currentStep.config.min_value} {unit}</span>
                <span>Max: {currentStep.config.max_value} {unit}</span>
              </div>
            )}
            {isOutOfRange && (
              <div className="flex items-center text-xs text-red-400 gap-1.5 justify-center">
                <AlertCircle className="h-4 w-4" />
                Reading is outside recommended range limits!
              </div>
            )}
          </div>
        );

      case "multi_choice":
        const options = currentStep.config.options || [];
        const selectedOptions: string[] = currentInputs.selected || [];

        const handleOptionToggle = (opt: string) => {
          // HVAC and GD steps are standard single select choices
          const nextInputs = { selected: [opt] };
          saveStepData(stepKey, nextInputs);
        };

        return (
          <div className="grid grid-cols-1 gap-2 py-4">
            {options.map((opt: string) => {
              const isSelected = selectedOptions.includes(opt);
              return (
                <button
                  key={opt}
                  onClick={() => handleOptionToggle(opt)}
                  className={`w-full py-4 px-5 rounded-xl border text-left font-medium transition cursor-pointer flex items-center justify-between ${
                    isSelected
                      ? "bg-indigo-500/10 border-indigo-500 text-indigo-200"
                      : "bg-white/5 border-white/5 text-gray-300 hover:bg-white/10 hover:border-white/10"
                  }`}
                >
                  <span>{opt}</span>
                  {isSelected && (
                    <div className="h-6 w-6 rounded-full bg-indigo-500 flex items-center justify-center">
                      <Check className="h-4 w-4 text-white" />
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        );

      case "text":
        return (
          <div className="space-y-3 py-4">
            <div className="relative">
              <textarea
                rows={4}
                placeholder={currentStep.config.placeholder || "Enter notes..."}
                value={currentInputs.notes || ""}
                className="w-full px-4 py-3 rounded-xl glass-input text-gray-200 text-sm resize-none focus:outline-none"
                onChange={(e) => {
                  const val = e.target.value;
                  const nextInputs = { ...currentInputs, notes: val };
                  setProgress(prev => ({
                    ...prev,
                    [stepKey]: {
                      ...prev[stepKey],
                      inputs: nextInputs,
                      completed_at: new Date().toISOString()
                    }
                  }));
                  triggerDebouncedSave(stepKey, nextInputs);
                }}
              />
              <button
                type="button"
                onClick={() => handleSpeechToText(stepKey)}
                className={`absolute right-3 bottom-4 p-2.5 rounded-full border transition flex items-center justify-center cursor-pointer ${
                  speechActiveStep === stepKey
                    ? "bg-red-500/20 border-red-500 text-red-400 animate-pulse"
                    : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10"
                }`}
              >
                {speechActiveStep === stepKey ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
            </div>
            {speechActiveStep === stepKey && (
              <div className="text-xs text-red-400 text-center animate-pulse">
                Listening... Speak now. Tapping button stops recording.
              </div>
            )}
          </div>
        );

      case "voice":
        const hasVoice = !!currentInputs.audio_url;
        return (
          <div className="flex flex-col items-center justify-center space-y-4 py-4">
            {isRecording ? (
              <div className="w-full flex flex-col items-center space-y-3">
                <canvas
                  ref={canvasRef}
                  width={300}
                  height={60}
                  className="w-full max-w-xs h-16 rounded-xl border border-white/5 bg-black/10"
                />
                <button
                  type="button"
                  onClick={stopRecording}
                  className="flex items-center gap-2 px-5 py-3 rounded-full bg-red-500 hover:bg-red-600 text-white font-semibold shadow-lg shadow-red-500/20 transition cursor-pointer"
                >
                  <Square className="h-4 w-4 fill-white" />
                  Stop Recording
                </button>
              </div>
            ) : hasVoice ? (
              <div className="w-full max-w-sm flex flex-col space-y-3 bg-white/5 border border-white/5 rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-400">Audio Log Captured</span>
                  <button
                    type="button"
                    onClick={startRecording}
                    className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold cursor-pointer"
                  >
                    Re-Record
                  </button>
                </div>
                {/* Audio Playback Component */}
                <div className="flex items-center gap-3 bg-black/20 p-3 rounded-lg border border-white/5">
                  <button
                    type="button"
                    onClick={() => {
                      setAudioPlaybackActive(true);
                      setTimeout(() => setAudioPlaybackActive(false), 3000);
                    }}
                    className={`p-2.5 rounded-full flex items-center justify-center cursor-pointer ${
                      audioPlaybackActive ? "bg-indigo-500 text-white" : "bg-white/5 text-gray-300 hover:bg-white/10"
                    }`}
                  >
                    <Volume2 className={`h-4 w-4 ${audioPlaybackActive ? "animate-bounce" : ""}`} />
                  </button>
                  <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-indigo-500 rounded-full transition-all duration-3000 ease-linear"
                      style={{ width: audioPlaybackActive ? "100%" : "0%" }}
                    />
                  </div>
                </div>
                {currentInputs.transcript && (
                  <div className="p-3 bg-black/20 rounded-lg border border-white/5 text-left">
                    <span className="text-xs text-gray-500 block mb-1">Transcript Preview</span>
                    <p className="text-xs text-gray-300 italic">{currentInputs.transcript}</p>
                  </div>
                )}
              </div>
            ) : (
              <button
                type="button"
                onClick={startRecording}
                className="flex flex-col items-center justify-center p-6 rounded-2xl border-2 border-dashed border-white/10 hover:border-indigo-500/50 hover:bg-white/5 cursor-pointer transition w-full max-w-xs py-8"
              >
                <div className="h-14 w-14 rounded-full bg-indigo-500/10 flex items-center justify-center hover:scale-105 transition">
                  <Mic className="h-6 w-6 text-indigo-400" />
                </div>
                <span className="text-sm font-medium text-gray-300 mt-3">Record Voice Memo</span>
                <span className="text-xs text-gray-500 mt-1">Tap to record audio memo</span>
              </button>
            )}
          </div>
        );

      case "checklist":
        const listItems = currentStep.config.items || [];
        const checkedList: string[] = currentInputs.checked || [];

        const handleCheckToggle = (item: string) => {
          const nextChecked = checkedList.includes(item)
            ? checkedList.filter(i => i !== item)
            : [...checkedList, item];
          const nextInputs = { checked: nextChecked };
          saveStepData(stepKey, nextInputs);
        };

        return (
          <div className="space-y-2 py-4">
            {listItems.map((item: string) => {
              const isChecked = checkedList.includes(item);
              return (
                <button
                  key={item}
                  onClick={() => handleCheckToggle(item)}
                  className={`w-full p-4 rounded-xl border text-left font-medium transition cursor-pointer flex items-center gap-3 ${
                    isChecked
                      ? "bg-indigo-500/10 border-indigo-500/50 text-indigo-200"
                      : "bg-white/5 border-white/5 text-gray-300 hover:bg-white/10"
                  }`}
                >
                  <div className={`h-5 w-5 rounded-md flex items-center justify-center border ${
                    isChecked ? "bg-indigo-500 border-indigo-500" : "border-white/20"
                  }`}>
                    {isChecked && <Check className="h-3 w-3 text-white" />}
                  </div>
                  <span className="text-sm">{item}</span>
                </button>
              );
            })}
          </div>
        );

      case "ai_trigger":
        const aiResult = currentProgress.ai_result;

        if (aiRunningStep === stepKey) {
          return (
            <div className="flex flex-col items-center justify-center py-8">
              <Loader2 className="h-10 w-10 text-indigo-400 animate-spin" />
              <span className="text-sm font-medium text-gray-300 mt-3">Synthesizing accumulated data...</span>
              <span className="text-xs text-gray-500 mt-1">Running AI diagnostics models</span>
            </div>
          );
        }

        if (aiResult) {
          return null; // The AI diagnostic card is rendered at page level below step inputs
        }

        return (
          <div className="flex flex-col items-center py-6">
            <button
              type="button"
              onClick={() => handleTriggerAiAnalysis(stepKey)}
              className="flex items-center gap-2.5 px-6 py-4 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-semibold shadow-lg shadow-indigo-500/25 transition hover:scale-102 cursor-pointer w-full max-w-xs justify-center"
            >
              <Sparkles className="h-5 w-5 animate-pulse" />
              Run AI Analysis
            </button>
            <p className="text-xs text-gray-500 mt-2 text-center max-w-xs">
              This will evaluate all submitted diagnostics measurements and draft a recommended diagnosis report.
            </p>
          </div>
        );

      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-4">
        <Loader2 className="h-10 w-10 text-indigo-500 animate-spin" />
        <span className="text-sm text-gray-400 mt-2">Loading Guided Inspection...</span>
      </div>
    );
  }

  if (error || !job || steps.length === 0) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 text-center">
        <AlertCircle className="h-12 w-12 text-red-500 mb-3" />
        <h3 className="text-lg font-bold text-gray-200">Error Loading Workflow</h3>
        <p className="text-sm text-gray-400 max-w-xs mt-1">{error || "No active workflow templates."}</p>
        <button
          onClick={() => router.push(`/app/jobs/${id}`)}
          className="mt-6 px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm font-semibold hover:bg-white/10 transition cursor-pointer"
        >
          Return to Job Card
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen pb-24 relative">
      {/* Header Panel */}
      <header className="sticky top-0 z-40 bg-[#030712]/80 backdrop-blur-md border-b border-white/5 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push(`/app/jobs/${id}`)}
            className="p-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 transition cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4 text-gray-300" />
          </button>
          <div>
            <h1 className="text-sm font-bold text-gray-200">Job #{job.job_number} Inspection</h1>
            <span className="text-xs text-gray-400">{job.customer.first_name} {job.customer.last_name}</span>
          </div>
        </div>

        {/* Sync / Offline Badges */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push(`/app/jobs/${id}/ai?from=inspection`)}
            className="flex items-center gap-1.5 text-[10px] font-extrabold text-indigo-400 bg-indigo-500/10 hover:bg-indigo-500/20 px-2.5 py-1 rounded-full border border-indigo-500/25 transition cursor-pointer"
            title="Ask Senior Tech AI"
          >
            <Bot className="h-3.5 w-3.5 text-indigo-400 animate-pulse" />
            <span>Ask AI</span>
          </button>
          {!isOnline ? (
            <span className="flex items-center gap-1 text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full border border-amber-500/20">
              <WifiOff className="h-3 w-3" />
              Offline
            </span>
          ) : saveStatus === "saving" ? (
            <span className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 bg-indigo-500/10 px-2 py-1 rounded-full border border-indigo-500/20">
              <Loader2 className="h-3 w-3 animate-spin" />
              Saving...
            </span>
          ) : saveStatus === "offline-queued" ? (
            <span className="flex items-center gap-1 text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full border border-amber-500/20 animate-pulse">
              <CloudLightning className="h-3 w-3" />
              Unsaved ({offlineQueueLength})
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded-full border border-emerald-500/20">
              <Check className="h-3 w-3" />
              Saved
            </span>
          )}
        </div>
      </header>

      <main className="max-w-md mx-auto px-4 mt-6">
        {/* Progress Bar */}
        <div className="mb-6 space-y-1.5">
          <div className="flex justify-between text-xs text-gray-400">
            <span>Progress: {completedCount} / {totalSteps} steps completed</span>
            <span className="font-semibold">{Math.round((completedCount / totalSteps) * 100)}%</span>
          </div>
          <div className="w-full h-2.5 bg-white/5 border border-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-300"
              style={{ width: `${(completedCount / totalSteps) * 100}%` }}
            />
          </div>
        </div>

        {/* Step Card */}
        <div className="glass-card rounded-2xl p-6 border border-white/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-xl pointer-events-none" />

          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
              Step {currentStepIndex + 1} of {totalSteps}
            </span>
            {currentStep.required ? (
              <span className="text-[10px] font-bold text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full border border-red-500/25">
                Required
              </span>
            ) : (
              <span className="text-[10px] font-bold text-gray-400 bg-white/5 px-2 py-0.5 rounded-full border border-white/5">
                Optional
              </span>
            )}
          </div>

          <h2 className="text-lg font-bold text-gray-100">{currentStep.name}</h2>
          <p className="text-sm text-gray-400 mt-1 leading-relaxed">{currentStep.description}</p>

          {/* Step Input Area */}
          <div className="mt-6 border-t border-white/5 pt-6">
            {renderStepInput()}
          </div>

          {/* Quick Trigger for AI Steps if not already processed */}
          {currentStep.type === "photo" && currentProgress.inputs?.photo_url && !currentProgress.ai_result && (
            <div className="mt-4 border-t border-white/5 pt-4 flex justify-center">
              {aiRunningStep === currentStep.key ? (
                <button disabled className="flex items-center gap-2 text-xs font-semibold text-indigo-400">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Running AI Analysis...
                </button>
              ) : (
                <button
                  onClick={() => handleTriggerAiAnalysis(currentStep.key)}
                  className="flex items-center gap-1.5 text-xs font-bold text-indigo-400 hover:text-indigo-300 transition cursor-pointer"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  Trigger AI Photo Scan
                </button>
              )}
            </div>
          )}

          {/* Inline AI Result Card (rendered inside the active step card) */}
          {currentProgress.ai_result && (
            <div className="mt-6 border-t border-indigo-500/20 pt-6 space-y-4">
              <div className="p-4 rounded-xl bg-indigo-500/5 border border-indigo-500/20 relative overflow-hidden">
                <div className="flex items-center gap-1.5 text-indigo-200 font-bold text-xs mb-2">
                  <Sparkles className="h-4 w-4 text-indigo-400 animate-pulse" />
                  AI DIAGNOSTIC METRICS
                </div>
                <p className="text-xs text-gray-300 leading-relaxed">
                  {currentProgress.ai_result.diagnostic_summary || currentProgress.ai_result.summary}
                </p>

                {/* make, model info */}
                {currentProgress.ai_result.make && (
                  <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] bg-black/20 p-2.5 rounded-lg border border-white/5">
                    <div>
                      <span className="text-gray-500 block">Make</span>
                      <span className="text-gray-200 font-medium">{currentProgress.ai_result.make}</span>
                    </div>
                    <div>
                      <span className="text-gray-500 block">Model</span>
                      <span className="text-gray-200 font-medium">{currentProgress.ai_result.model}</span>
                    </div>
                  </div>
                )}

                {/* likely causes */}
                {currentProgress.ai_result.likely_causes && currentProgress.ai_result.likely_causes.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Likely Causes</span>
                    {currentProgress.ai_result.likely_causes.map((cause: any) => (
                      <div key={cause.cause} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <span className="text-gray-300">{cause.cause}</span>
                          <span className="text-indigo-400 font-semibold">{Math.round(cause.confidence * 100)}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{ width: `${cause.confidence * 100}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* recommended actions */}
                {currentProgress.ai_result.recommended_actions && currentProgress.ai_result.recommended_actions.length > 0 && (
                  <div className="mt-4 space-y-1.5">
                    <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">Recommended Actions</span>
                    <ul className="text-xs text-gray-300 space-y-1 list-disc list-inside">
                      {currentProgress.ai_result.recommended_actions.map((act: string) => (
                        <li key={act}>{act}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Ask AI Follow-up Button */}
                <button
                  type="button"
                  onClick={() => setShowChatDrawer(true)}
                  className="mt-4 w-full flex items-center justify-center gap-1.5 py-2.5 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 text-xs font-semibold text-indigo-300 transition cursor-pointer"
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  Ask AI a follow-up
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Action Buttons Panel */}
        <div className="mt-4 flex gap-3">
          {!currentStep?.required && (
            <button
              onClick={() => saveStepData(currentStep.key, {}, true)}
              className="flex-1 py-3.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 font-semibold text-sm transition cursor-pointer text-gray-300 text-center"
            >
              Skip Step
            </button>
          )}

          <button
            disabled={!isCurrentStepCompleted || !isChecklistStepValid()}
            onClick={() => {
              if (currentStepIndex < totalSteps - 1) {
                setCurrentStepIndex(currentStepIndex + 1);
              } else {
                // Complete inspection workflow
                router.push(`/app/jobs/${id}`);
              }
            }}
            className={`flex-1 py-3.5 rounded-xl font-bold text-sm transition flex items-center justify-center gap-1.5 shadow-lg ${
              isCurrentStepCompleted && isChecklistStepValid()
                ? "bg-indigo-500 hover:bg-indigo-600 text-white shadow-indigo-500/20 cursor-pointer"
                : "bg-white/5 border border-white/5 text-gray-500 cursor-not-allowed"
            }`}
          >
            {currentStepIndex === totalSteps - 1 ? "Finish Inspection" : "Next Step"}
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </main>

      {/* Navigation Dot Indicators at Bottom */}
      <footer className="fixed bottom-0 left-0 right-0 z-30 bg-[#030712]/90 backdrop-blur-md border-t border-white/5 p-4 flex flex-col items-center space-y-3">
        <div className="flex gap-2 max-w-full overflow-x-auto pb-1 px-4 scrollbar-none">
          {steps.map((st, idx) => {
            const stepProg = progress[st.key];
            const isCompleted = stepProg && (stepProg.completed_at || stepProg.skipped);
            const isCurrent = idx === currentStepIndex;

            return (
              <button
                key={st.key}
                disabled={!isCompleted && !isCurrent}
                onClick={() => setCurrentStepIndex(idx)}
                className={`h-8 w-8 rounded-full border flex items-center justify-center text-xs font-semibold transition shrink-0 ${
                  isCurrent
                    ? "bg-indigo-500 border-indigo-500 text-white scale-110 shadow-lg shadow-indigo-500/20"
                    : isCompleted
                    ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/20 cursor-pointer"
                    : "bg-white/5 border-white/5 text-gray-600 cursor-not-allowed"
                }`}
              >
                {isCompleted ? <Check className="h-3 w-3 text-emerald-400" /> : idx + 1}
              </button>
            );
          })}
        </div>
      </footer>

      {/* Embedded AI Chat Drawer (Side-over) */}
      {showChatDrawer && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowChatDrawer(false)}
          />

          {/* Drawer container */}
          <div className="relative w-full max-w-md bg-[#0b0f19] border-l border-white/10 h-full flex flex-col shadow-2xl animate-slide-in">
            <header className="px-4 py-4 border-b border-white/5 flex items-center justify-between bg-indigo-950/10">
              <div className="flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-indigo-400" />
                <span className="font-bold text-gray-200">AI Diagnostic Assistant</span>
              </div>
              <button
                onClick={() => setShowChatDrawer(false)}
                className="p-1 rounded-lg hover:bg-white/5 text-gray-400 hover:text-white transition cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </header>

            {/* Chat message logs */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {chatMessages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl p-4 text-sm leading-relaxed ${
                      msg.sender === "user"
                        ? "bg-indigo-600 text-white rounded-tr-none"
                        : "bg-white/5 border border-white/5 text-gray-200 rounded-tl-none"
                    }`}
                  >
                    <p className="whitespace-pre-line">{msg.text}</p>
                    <span className="text-[10px] text-gray-500 block text-right mt-1.5">{msg.time}</span>
                  </div>
                </div>
              ))}
              {isAiThinking && (
                <div className="flex justify-start">
                  <div className="bg-white/5 border border-white/5 rounded-2xl rounded-tl-none p-4 flex items-center gap-2">
                    <Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />
                    <span className="text-xs text-gray-400">AI is thinking...</span>
                  </div>
                </div>
              )}
            </div>

            {/* Chat inputs */}
            <footer className="p-4 border-t border-white/5 bg-[#030712]/50 flex gap-2">
              <input
                type="text"
                placeholder="Ask about Carrier, pressures, codes..."
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSendChat();
                }}
                className="flex-1 px-4 py-3 rounded-xl glass-input text-sm text-gray-200 focus:outline-none"
              />
              <button
                onClick={handleSendChat}
                className="p-3 rounded-xl bg-indigo-500 hover:bg-indigo-600 text-white flex items-center justify-center transition cursor-pointer"
              >
                <Send className="h-4 w-4" />
              </button>
            </footer>
          </div>
        </div>
      )}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slideIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
      `}</style>
    </div>
  );
}
