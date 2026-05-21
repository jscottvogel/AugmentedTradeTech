"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../../../../hooks/useAuth";
import { AuthGuard } from "../../../../../components/AuthGuard";
import { offlineSafeFetch } from "../../../../../utils/apiClient";
import {
  ArrowLeft,
  Bot,
  Mic,
  Send,
  AlertTriangle,
  FileText,
  Check,
  Loader2,
  Sparkles,
  WifiOff,
  User,
  Plus
} from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export default function SeniorTechChatScreen() {
  return (
    <AuthGuard>
      <SeniorTechChatContent />
    </AuthGuard>
  );
}

function SeniorTechChatContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken } = useAuth();
  
  const id = params.id as string;
  const fromSource = searchParams.get("from") || "job_card";

  // State Management
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isOnline, setIsOnline] = useState(true);
  const [showToast, setShowToast] = useState<string | null>(null);
  const [toastError, setToastError] = useState(false);
  const [cachedDiagnosis, setCachedDiagnosis] = useState<any | null>(null);
  const [showOfflineDiag, setShowOfflineDiag] = useState(false);

  // References
  const chatEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  // Suggested Quick Questions
  const suggestedQuestions = [
    "What are the likely causes?",
    "What parts do I need?",
    "Is this safe to operate?",
    "How do I test this?"
  ];

  // 1. Monitor network connectivity
  useEffect(() => {
    setIsOnline(window.navigator.onLine);
    const handleOnline = () => {
      setIsOnline(true);
      drainOfflineQueue();
    };
    const handleOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // 2. Load conversation history and cached diagnosis from LocalStorage
  useEffect(() => {
    if (!id) return;
    
    // Load messages
    const savedMessages = localStorage.getItem(`att-chat-history-${id}`);
    if (savedMessages) {
      try {
        setMessages(JSON.parse(savedMessages));
      } catch (e) {
        console.error("Failed to parse chat history:", e);
      }
    } else {
      // Seed initial welcoming message
      const welcomeMsg: Message = {
        id: `welcome-${Date.now()}`,
        role: "assistant",
        content: "Hey there! I'm your Senior Tech assistant. Ask me anything about this equipment, expected measurements, or how to tackle this job safely. What's going on?",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      setMessages([welcomeMsg]);
      localStorage.setItem(`att-chat-history-${id}`, JSON.stringify([welcomeMsg]));
    }

    // Load cached diagnosis
    const savedDiag = localStorage.getItem(`att-cached-diagnosis-${id}`);
    if (savedDiag) {
      try {
        setCachedDiagnosis(JSON.parse(savedDiag));
      } catch (e) {
        console.error("Failed to parse cached diagnosis:", e);
      }
    }
  }, [id]);

  // 3. Keep scroll at bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // 4. Fetch job details when online to update the cached diagnosis
  useEffect(() => {
    if (!isOnline || !accessToken || !id) return;
    const fetchJobForCache = async () => {
      try {
        const res = await fetch(`${API_URL}/jobs/${id}`, {
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.ai_diagnosis) {
            setCachedDiagnosis(data.ai_diagnosis);
            localStorage.setItem(`att-cached-diagnosis-${id}`, JSON.stringify(data.ai_diagnosis));
          }
        }
      } catch (e) {
        console.error("Failed to prefetch job details for cache:", e);
      }
    };
    fetchJobForCache();
  }, [isOnline, accessToken, id]);

  // 5. Toast timer helper
  const triggerToast = (msg: string, isErr = false) => {
    setShowToast(msg);
    setToastError(isErr);
    setTimeout(() => {
      setShowToast(null);
      setToastError(false);
    }, 3000);
  };

  // 6. Handle SSE Streaming to fetch Claude responses
  const initiateStream = async (chatHistory: Message[]) => {
    if (!accessToken) return;
    setIsStreaming(true);

    // Create an empty placeholder message for the incoming streaming response
    const streamMessageId = `stream-${Date.now()}`;
    const newAiMessage: Message = {
      id: streamMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    setMessages((prev) => [...prev, newAiMessage]);

    try {
      const response = await fetch(`${API_URL}/ai/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          job_id: id,
          messages: chatHistory.map((m) => ({
            role: m.role,
            content: m.content
          }))
        })
      });

      if (!response.ok) {
        throw new Error("API streaming error");
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("ReadableStream not supported");

      let accumulatedText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n\n");

        for (const line of lines) {
          if (line.startsWith("data:")) {
            const dataStr = line.replace("data:", "").trim();
            if (!dataStr) continue;

            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.text) {
                accumulatedText += parsed.text;
                // Update the placeholder AI message content in real time
                setMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === streamMessageId
                      ? { ...msg, content: accumulatedText }
                      : msg
                  )
                );
              } else if (parsed.error) {
                throw new Error(parsed.error);
              }
            } catch (err) {
              console.warn("Failed to parse chunk line:", err);
            }
          }
        }
      }

      // Persist final updated messages array to local storage
      setMessages((prev) => {
        const finalMessages = prev.map((msg) =>
          msg.id === streamMessageId ? { ...msg, content: accumulatedText } : msg
        );
        localStorage.setItem(`att-chat-history-${id}`, JSON.stringify(finalMessages));
        return finalMessages;
      });

    } catch (err: any) {
      console.error("Streaming failed:", err);
      // Update placeholder with failure warning
      setMessages((prev) => {
        const finalMessages = prev.map((msg) =>
          msg.id === streamMessageId
            ? { ...msg, content: "Sorry, I ran into a connection issue. Let's try that again once you've got a stable network." }
            : msg
        );
        localStorage.setItem(`att-chat-history-${id}`, JSON.stringify(finalMessages));
        return finalMessages;
      });
      triggerToast("Failed to stream AI response", true);
    } finally {
      setIsStreaming(false);
    }
  };

  // 7. Send user input message
  const handleSendMessage = async (textToSend: string) => {
    if (!textToSend.trim()) return;

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: "user",
      content: textToSend.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    localStorage.setItem(`att-chat-history-${id}`, JSON.stringify(updatedMessages));
    setInput("");

    if (!isOnline) {
      // Queue message offline
      const offlineQueue = JSON.parse(localStorage.getItem(`att-offline-chat-queue-${id}`) || "[]");
      offlineQueue.push(userMsg);
      localStorage.setItem(`att-offline-chat-queue-${id}`, JSON.stringify(offlineQueue));

      // Append system message letting tech know it is queued
      const systemQueuedMsg: Message = {
        id: `queued-sys-${Date.now()}`,
        role: "assistant",
        content: "[Offline Mode] Your message has been queued. I'll process and respond as soon as your device reconnects to the network.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      };
      const finalOfflineMessages = [...updatedMessages, systemQueuedMsg];
      setMessages(finalOfflineMessages);
      localStorage.setItem(`att-chat-history-${id}`, JSON.stringify(finalOfflineMessages));
      return;
    }

    // Trigger SSE request
    await initiateStream(updatedMessages);
  };

  // 8. Drain offline queue when returning online
  const drainOfflineQueue = async () => {
    const queueKey = `att-offline-chat-queue-${id}`;
    const offlineQueue: Message[] = JSON.parse(localStorage.getItem(queueKey) || "[]");
    if (offlineQueue.length === 0) return;

    // Clear queue from storage first
    localStorage.removeItem(queueKey);

    // Retrieve full chat history
    let savedMessages: Message[] = JSON.parse(localStorage.getItem(`att-chat-history-${id}`) || "[]");
    
    // Filter out previous offline placeholder warning system notes to keep conversation history clean
    savedMessages = savedMessages.filter(m => !m.content.startsWith("[Offline Mode]"));

    // Send the last queued message to get response
    const lastUserMessageIndex = savedMessages.map(m => m.role).lastIndexOf("user");
    if (lastUserMessageIndex !== -1) {
      const sliceHistory = savedMessages.slice(0, lastUserMessageIndex + 1);
      setMessages(sliceHistory);
      localStorage.setItem(`att-chat-history-${id}`, JSON.stringify(sliceHistory));
      await initiateStream(sliceHistory);
    }
  };

  // 9. Add message content to Job Notes
  const handleAddToJobNotes = async (bodyText: string) => {
    if (!accessToken) return;
    try {
      const res = await offlineSafeFetch(`${API_URL}/jobs/${id}/notes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          body: `[AI Senior Tech Advice]: ${bodyText}`,
          note_type: "general",
          is_internal: true
        })
      });

      if (!res.ok) throw new Error("Failed to add note");

      triggerToast("Added to Job Notes successfully!");
    } catch (e) {
      console.error(e);
      triggerToast("Failed to save note", true);
    }
  };

  // 10. Voice input transcription (Speech-to-Text)
  const handleVoiceInput = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please use Chrome or Safari.");
      return;
    }

    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    setIsRecording(true);
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
    };

    recognition.onerror = (err: any) => {
      console.error("Speech input error:", err);
      setIsRecording(false);
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  // 11. Navigation back helper
  const handleBackNavigation = () => {
    if (fromSource === "inspection") {
      router.push(`/app/jobs/${id}/inspection`);
    } else {
      router.push(`/app/jobs/${id}`);
    }
  };

  return (
    <div className="min-h-screen bg-[#030712] text-white flex flex-col relative overflow-hidden font-sans">
      {/* Background radial glows */}
      <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/5 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-purple-500/5 blur-[120px] pointer-events-none" />

      {/* Header Bar */}
      <header className="sticky top-0 z-40 bg-[#030712]/85 backdrop-blur-lg border-b border-white/5 px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={handleBackNavigation}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 text-gray-300 hover:text-white transition cursor-pointer flex items-center justify-center"
          >
            <ArrowLeft className="h-4.5 w-4.5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center">
              <Bot className="h-4 w-4 text-indigo-400 animate-pulse" />
            </div>
            <div>
              <h1 className="text-sm font-extrabold text-gray-100 tracking-tight flex items-center gap-1.5">
                Senior Tech AI Mentor
                <Sparkles className="h-3 w-3 text-indigo-400 fill-indigo-400/30" />
              </h1>
              <p className="text-[10px] text-indigo-300 font-medium">Assigned to Job #{id ? id.substring(0, 8).toUpperCase() : ""}</p>
            </div>
          </div>
        </div>

        {/* Sync/Online Badges */}
        <div className="flex items-center">
          {!isOnline ? (
            <span className="flex items-center gap-1 text-[10px] font-bold text-amber-400 bg-amber-500/10 px-2.5 py-1 rounded-full border border-amber-500/20">
              <WifiOff className="h-3.5 w-3.5" />
              Offline Mode
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Mentor Online
            </span>
          )}
        </div>
      </header>

      {/* Offline Alert Banner */}
      {!isOnline && (
        <div className="bg-gradient-to-r from-amber-500/10 to-amber-600/15 border-b border-amber-500/20 px-4 py-2.5 flex items-center gap-2.5 text-xs text-amber-200/90 font-medium animate-fadeIn">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
          <span>AI chat requires connection. Sent messages will queue and sync when reconnected.</span>
        </div>
      )}

      {/* Main Chat Log */}
      <main className="flex-1 overflow-y-auto px-4 py-6 space-y-4 max-w-2xl mx-auto w-full">
        {/* Offline Diagnosis Cache reference */}
        {cachedDiagnosis && (
          <div className="bg-[#0b0f19]/60 border border-white/5 rounded-2xl p-4 overflow-hidden relative shadow-lg">
            <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-xl pointer-events-none" />
            <button
              onClick={() => setShowOfflineDiag(!showOfflineDiag)}
              className="w-full flex items-center justify-between text-xs font-bold text-indigo-300 hover:text-indigo-200 transition"
            >
              <div className="flex items-center gap-1.5">
                <FileText className="h-4 w-4" />
                <span>Reference: Cached AI Diagnosis ({!isOnline ? "Offline Ready" : "Online"})</span>
              </div>
              <span className="text-[10px] bg-indigo-500/15 px-2 py-0.5 rounded-md">
                {showOfflineDiag ? "Hide" : "Show"}
              </span>
            </button>
            
            {showOfflineDiag && (
              <div className="mt-3 pt-3 border-t border-white/5 space-y-2.5 text-xs text-gray-300 animate-fadeIn">
                <div>
                  <span className="font-bold text-gray-100 block mb-0.5">Summary:</span>
                  <p className="leading-relaxed text-gray-400">{cachedDiagnosis.summary}</p>
                </div>
                {cachedDiagnosis.root_causes && cachedDiagnosis.root_causes.length > 0 && (
                  <div>
                    <span className="font-bold text-gray-100 block mb-0.5">Potential Causes:</span>
                    <ul className="list-disc list-inside space-y-0.5 text-gray-400">
                      {cachedDiagnosis.root_causes.map((rc: any, idx: number) => (
                        <li key={idx}><span className="font-semibold text-gray-300">{rc.component}</span>: {rc.cause}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {cachedDiagnosis.recommendations && cachedDiagnosis.recommendations.length > 0 && (
                  <div>
                    <span className="font-bold text-gray-100 block mb-0.5">Recommendations:</span>
                    <ul className="list-disc list-inside space-y-0.5 text-gray-400">
                      {cachedDiagnosis.recommendations.map((rec: string, idx: number) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Message Logs */}
        <div className="space-y-4 pb-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-fadeIn`}
            >
              <div className="flex gap-2 max-w-[85%]">
                {msg.role === "assistant" && (
                  <div className="w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center shrink-0 mt-1">
                    <Bot className="h-3.5 w-3.5 text-indigo-400" />
                  </div>
                )}
                
                <div className="space-y-1">
                  <div
                    className={`rounded-2xl p-4 text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-indigo-600 text-white rounded-tr-none shadow-md shadow-indigo-500/10"
                        : "bg-white/5 border border-white/5 text-gray-200 rounded-tl-none"
                    }`}
                  >
                    <p className="whitespace-pre-line">{msg.content}</p>
                    
                    {/* Add to Notes Button */}
                    {msg.role === "assistant" && msg.content && !msg.content.includes("welcoming") && (
                      <div className="mt-3 pt-2 border-t border-white/5 flex justify-between items-center">
                        <span className="text-[9px] text-gray-500">{msg.timestamp}</span>
                        <button
                          onClick={() => handleAddToJobNotes(msg.content)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/5 hover:bg-indigo-500/10 border border-white/5 hover:border-indigo-500/25 text-[9px] font-bold text-gray-400 hover:text-indigo-300 transition cursor-pointer"
                        >
                          <Plus className="h-3 w-3" />
                          <span>Add to Job Notes</span>
                        </button>
                      </div>
                    )}
                    {msg.role === "user" && (
                      <span className="text-[9px] text-indigo-300/80 block text-right mt-1.5">{msg.timestamp}</span>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {isStreaming && (
            <div className="flex justify-start animate-pulse">
              <div className="flex gap-2 max-w-[85%]">
                <div className="w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center shrink-0 mt-1">
                  <Loader2 className="h-3.5 w-3.5 text-indigo-400 animate-spin" />
                </div>
                <div className="bg-white/5 border border-white/5 rounded-2xl rounded-tl-none p-4 flex items-center gap-2">
                  <span className="text-xs text-gray-400">Senior tech is typing</span>
                  <span className="flex gap-1">
                    <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </span>
                </div>
              </div>
            </div>
          )}
          
          <div ref={chatEndRef} />
        </div>
      </main>

      {/* Suggested Quick Questions Chips */}
      {messages.length > 0 && !isStreaming && (
        <div className="max-w-2xl mx-auto w-full px-4 py-2 flex gap-2 overflow-x-auto select-none shrink-0 scrollbar-none">
          {suggestedQuestions.map((q) => (
            <button
              key={q}
              onClick={() => handleSendMessage(q)}
              className="px-3 py-1.5 rounded-full bg-[#0b0f19] border border-white/5 hover:border-indigo-500/35 text-[10px] text-gray-300 hover:text-indigo-300 font-bold transition shrink-0 cursor-pointer"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Chat Form Footer */}
      <footer className="sticky bottom-0 z-40 bg-[#030712]/90 backdrop-blur-lg border-t border-white/5 px-4 py-4 shrink-0">
        <div className="max-w-2xl mx-auto w-full flex items-center gap-2">
          {/* Voice Input STT Button */}
          <button
            onClick={handleVoiceInput}
            className={`p-3 rounded-xl flex items-center justify-center transition shrink-0 cursor-pointer ${
              isRecording
                ? "bg-red-500 text-white animate-pulse border border-red-400"
                : "bg-white/5 hover:bg-white/10 text-gray-300 border border-white/5 hover:border-white/10"
            }`}
            title="Speech-to-Text voice memo dictation"
          >
            <Mic className={`h-4.5 w-4.5 ${isRecording ? "scale-110" : ""}`} />
          </button>

          {/* Text Input */}
          <input
            type="text"
            placeholder={
              !isOnline
                ? "Type a message to queue..."
                : isRecording
                ? "Listening..."
                : "Ask senior tech about measurements, codes..."
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSendMessage(input);
            }}
            disabled={isStreaming}
            className="flex-1 bg-[#0b0f19] border border-white/5 text-xs text-white rounded-xl px-4 py-3 placeholder:text-gray-600 focus:outline-none focus:border-indigo-500 transition"
          />

          {/* Send Button */}
          <button
            onClick={() => handleSendMessage(input)}
            disabled={isStreaming || !input.trim()}
            className={`p-3 rounded-xl flex items-center justify-center transition shrink-0 cursor-pointer ${
              input.trim() && !isStreaming
                ? "bg-indigo-500 hover:bg-indigo-600 text-white shadow-md shadow-indigo-500/25"
                : "bg-white/5 text-gray-500 border border-white/5 cursor-not-allowed"
            }`}
          >
            <Send className="h-4.5 w-4.5" />
          </button>
        </div>
      </footer>

      {/* Floating Glassmorphic Toast Notifications */}
      {showToast && (
        <div className="fixed bottom-24 left-1/2 transform -translate-x-1/2 z-50 animate-slide-up">
          <div
            className={`px-4 py-2.5 rounded-full border shadow-xl flex items-center gap-2 text-xs font-semibold ${
              toastError
                ? "bg-red-950/80 border-red-500/35 text-red-200"
                : "bg-indigo-950/80 border-indigo-500/35 text-indigo-200"
            } backdrop-blur-md`}
          >
            {toastError ? (
              <AlertTriangle className="h-4 w-4 text-red-400" />
            ) : (
              <Check className="h-4 w-4 text-indigo-400" />
            )}
            <span>{showToast}</span>
          </div>
        </div>
      )}

      {/* Global Slide-up Animation styles */}
      <style>{`
        @keyframes slideUp {
          from { transform: translate(-50%, 1rem); }
          to { transform: translate(-50%, 0); }
        }
        .animate-slide-up {
          animation: slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        @keyframes fadeIn {
          from { transform: translateY(2px); }
          to { transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .scrollbar-none::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-none {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
    </div>
  );
}
