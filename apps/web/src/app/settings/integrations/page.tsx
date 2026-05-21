"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useAuth } from "../../../hooks/useAuth";
import { AuthGuard } from "../../../components/AuthGuard";
import {
  ArrowLeft,
  CheckCircle,
  Clock,
  Sparkles,
  Loader2,
  ShieldAlert,
  Settings,
  AlertCircle,
  RefreshCw,
  Power,
  Save,
  Database,
  HelpCircle,
  Check
} from "lucide-react";

export default function IntegrationsSettingsPage() {
  return (
    <AuthGuard>
      <Suspense fallback={
        <div className="min-h-screen flex items-center justify-center bg-slate-950 px-4 font-sans text-slate-100">
          <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
        </div>
      }>
        <IntegrationsContent />
      </Suspense>
    </AuthGuard>
  );
}

function IntegrationsContent() {
  const { accessToken, user } = useAuth();
  const searchParams = useSearchParams();
  const router = useRouter();

  const mockCallback = searchParams.get("mock_callback");
  const code = searchParams.get("code");
  const realmId = searchParams.get("realmId");
  const state = searchParams.get("state");
  const statusParam = searchParams.get("status");
  const errorParam = searchParams.get("error");

  const [connected, setConnected] = useState<boolean>(false);
  const [realmIdVal, setRealmIdVal] = useState<string | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [laborMapping, setLaborMapping] = useState<string>("Labor");
  const [partMapping, setPartMapping] = useState<string>("Parts");
  const [feeMapping, setFeeMapping] = useState<string>("Fee");
  const [errorsList, setErrorsList] = useState<any[]>([]);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSavingMappings, setIsSavingMappings] = useState<boolean>(false);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [isDisconnecting, setIsDisconnecting] = useState<boolean>(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const [toastMessage, setToastMessage] = useState<{ text: string; type: "success" | "error" } | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Handle mock callback redirecting to backend
  useEffect(() => {
    if (mockCallback && code && realmId && state) {
      window.location.href = `${API_URL}/integrations/qbo/callback?code=${code}&realmId=${realmId}&state=${state}`;
    }
  }, [mockCallback, code, realmId, state, API_URL]);

  // Handle URL status / error params
  useEffect(() => {
    if (statusParam === "success") {
      showToast("Successfully connected to QuickBooks Online!", "success");
      // Clean query parameters
      router.replace("/settings/integrations");
    } else if (statusParam === "error") {
      let msg = "Failed to connect to QuickBooks Online.";
      if (errorParam === "session_expired") msg = "OAuth session expired. Please try again.";
      if (errorParam === "invalid_session") msg = "Invalid session state. Please try again.";
      if (errorParam === "token_exchange_failed") msg = "Failed to exchange OAuth token with QuickBooks.";
      showToast(msg, "error");
      router.replace("/settings/integrations");
    }
  }, [statusParam, errorParam, router]);

  const showToast = (text: string, type: "success" | "error" = "success") => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  const fetchStatus = async () => {
    if (!accessToken) return;
    setIsLoading(true);
    try {
      const res = await fetch(`${API_URL}/integrations/qbo/status`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) throw new Error("Failed to fetch QuickBooks status");
      const data = await res.json();
      setConnected(data.connected);
      setRealmIdVal(data.realm_id);
      setLastSyncAt(data.last_sync_at);
      if (data.item_mappings) {
        setLaborMapping(data.item_mappings.labor || "Labor");
        setPartMapping(data.item_mappings.part_fallback || "Parts");
        setFeeMapping(data.item_mappings.fee || "Fee");
      }
      setErrorsList(data.errors || []);
    } catch (err: any) {
      showToast("Error loading integrations status: " + err.message, "error");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (accessToken) {
      fetchStatus();
    }
  }, [accessToken]);

  const handleConnect = async () => {
    setIsConnecting(true);
    try {
      const res = await fetch(`${API_URL}/integrations/qbo/connect`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      });
      if (!res.ok) throw new Error("Failed to initiate connection");
      const data = await res.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err: any) {
      showToast(err.message, "error");
      setIsConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect QuickBooks Online?")) return;
    setIsDisconnecting(true);
    try {
      const res = await fetch(`${API_URL}/integrations/qbo/disconnect`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) throw new Error("Failed to disconnect");
      showToast("QuickBooks Online disconnected successfully.", "success");
      setConnected(false);
      setRealmIdVal(null);
      setErrorsList([]);
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setIsDisconnecting(false);
    }
  };

  const handleSaveMappings = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingMappings(true);
    try {
      const res = await fetch(`${API_URL}/integrations/qbo/mappings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          labor: laborMapping,
          part_fallback: partMapping,
          fee: feeMapping,
        }),
      });
      if (!res.ok) throw new Error("Failed to save mappings");
      showToast("Item mappings saved successfully.", "success");
    } catch (err: any) {
      showToast(err.message, "error");
    } finally {
      setIsSavingMappings(false);
    }
  };

  const handleRetrySync = async (syncId: string, invoiceId: string) => {
    setRetryingId(syncId);
    try {
      const res = await fetch(`${API_URL}/integrations/qbo/sync/${invoiceId}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) throw new Error("Failed to trigger sync retry");
      showToast("Sync task enqueued. Refreshing list in 3 seconds...", "success");
      setTimeout(() => {
        fetchStatus();
        setRetryingId(null);
      }, 3000);
    } catch (err: any) {
      showToast(err.message, "error");
      setRetryingId(null);
    }
  };

  const isAdmin = user?.role === "company_admin";

  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950 px-4 font-sans text-slate-100">
        <div className="max-w-md p-8 rounded-2xl bg-slate-900/40 backdrop-blur-md border border-slate-800 text-center shadow-2xl flex flex-col items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
            <ShieldAlert className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-red-500">Access Denied</h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            Only company administrators can access QuickBooks Online settings.
          </p>
          <Link 
            href="/" 
            className="mt-2 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs font-semibold transition"
          >
            Return to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-6 py-10 max-w-6xl mx-auto flex flex-col gap-8">
      
      {/* Toast Alert Popover */}
      {toastMessage && (
        <div className={`fixed bottom-8 right-8 z-50 flex items-center gap-2 px-5 py-3 rounded-xl glass-card border-l-4 ${toastMessage.type === "success" ? "border-emerald-500 text-emerald-100" : "border-rose-500 text-rose-100"} shadow-2xl text-sm font-medium animate-in fade-in slide-in-from-bottom-5`}>
          {toastMessage.type === "success" ? (
            <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}

      {/* Header Container */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div className="space-y-1">
          <Link href="/" className="inline-flex items-center gap-1 text-slate-500 hover:text-indigo-400 text-xs font-semibold mb-2 transition-colors">
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Dashboard
          </Link>
          <h1 className="text-3xl font-extrabold bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-500 bg-clip-text text-transparent tracking-tight">
            QuickBooks Online Integration
          </h1>
          <p className="text-sm text-slate-400">
            Automatically synchronize paid invoices, customers, and invoice payments directly to QuickBooks.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
          <span className="text-sm text-slate-400 font-medium">Loading integration status...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Left Column: Connection Details */}
          <div className="lg:col-span-1 flex flex-col gap-8">
            <div className="glass-card rounded-2xl p-6 relative overflow-hidden shadow-xl">
              <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-2xl pointer-events-none" />
              
              <h2 className="text-lg font-bold text-slate-200 mb-4 flex items-center gap-2 font-sans">
                <Database className="w-5 h-5 text-indigo-400" />
                Connection Status
              </h2>

              {connected ? (
                <div className="space-y-6">
                  <div className="flex items-center gap-3">
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
                    </span>
                    <div>
                      <span className="text-sm font-semibold text-emerald-400 block">Connected</span>
                      <span className="text-xs text-slate-500 font-mono">{realmIdVal}</span>
                    </div>
                  </div>

                  {lastSyncAt && (
                    <div className="text-xs text-slate-400 space-y-1">
                      <span className="text-slate-500 block font-semibold">Last Successful Sync:</span>
                      <span className="flex items-center gap-1.5 font-medium">
                        <Clock className="w-3.5 h-3.5 text-indigo-400" />
                        {new Date(lastSyncAt).toLocaleString()}
                      </span>
                    </div>
                  )}

                  <button
                    onClick={handleDisconnect}
                    disabled={isDisconnecting}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-rose-500/10 hover:bg-rose-500/20 active:scale-[0.98] border border-rose-500/20 text-rose-300 font-bold text-sm rounded-xl cursor-pointer transition-all duration-200 disabled:opacity-50"
                  >
                    {isDisconnecting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Power className="w-4 h-4" />
                    )}
                    Disconnect QuickBooks
                  </button>
                </div>
              ) : (
                <div className="space-y-6">
                  <p className="text-xs text-slate-400 leading-relaxed font-medium">
                    Connect your QuickBooks Online account to synchronize invoices. We support auto-customer matching by email/phone and fallback item mapping.
                  </p>
                  
                  <button
                    onClick={handleConnect}
                    disabled={isConnecting}
                    className="w-full flex items-center justify-center gap-2 px-5 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] text-white font-bold text-sm rounded-xl cursor-pointer shadow-lg shadow-indigo-500/10 transition-all duration-200 disabled:opacity-50"
                  >
                    {isConnecting ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                    Connect QuickBooks
                  </button>
                </div>
              )}
            </div>

            <div className="glass-card rounded-2xl p-6 relative overflow-hidden shadow-xl">
              <h3 className="text-sm font-bold text-slate-300 mb-2 flex items-center gap-1.5 font-sans">
                <HelpCircle className="w-4.5 h-4.5 text-slate-400" />
                How Sync Works
              </h3>
              <ul className="text-xs text-slate-400 space-y-2 list-disc list-inside font-medium leading-relaxed">
                <li>Paid invoices automatically queue for sync.</li>
                <li>Customer accounts are resolved by email/phone.</li>
                <li>Invoice line items are mapped to QBO Service / Non-Inventory Items.</li>
                <li>Receipt of payment matches the invoice directly.</li>
              </ul>
            </div>
          </div>

          {/* Right Columns: Configuration and Failed Syncs */}
          <div className="lg:col-span-2 flex flex-col gap-8">
            
            {/* Item Mapping Configuration (Only if connected) */}
            {connected && (
              <div className="glass-card rounded-2xl p-6 relative overflow-hidden shadow-xl">
                <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/5 rounded-full blur-2xl pointer-events-none" />
                
                <h2 className="text-lg font-bold text-slate-200 mb-4 flex items-center gap-2 font-sans">
                  <Settings className="w-5 h-5 text-indigo-400" />
                  Item Mapping Configuration
                </h2>
                
                <form onSubmit={handleSaveMappings} className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-400 block">
                        Labor Service Item
                      </label>
                      <input
                        type="text"
                        required
                        value={laborMapping}
                        onChange={(e) => setLaborMapping(e.target.value)}
                        className="w-full px-4 py-2.5 rounded-xl text-slate-100 glass-input text-sm outline-none font-medium"
                      />
                      <span className="text-[10px] text-slate-500 block font-medium">
                        Map labor invoice items to this QuickBooks item name.
                      </span>
                    </div>

                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-slate-400 block">
                        Fees Service Item
                      </label>
                      <input
                        type="text"
                        required
                        value={feeMapping}
                        onChange={(e) => setFeeMapping(e.target.value)}
                        className="w-full px-4 py-2.5 rounded-xl text-slate-100 glass-input text-sm outline-none font-medium"
                      />
                      <span className="text-[10px] text-slate-500 block font-medium">
                        Map platform fees to this QuickBooks item name.
                      </span>
                    </div>

                    <div className="space-y-2 md:col-span-2">
                      <label className="text-xs font-semibold text-slate-400 block">
                        Parts Fallback Item
                      </label>
                      <input
                        type="text"
                        required
                        value={partMapping}
                        onChange={(e) => setPartMapping(e.target.value)}
                        className="w-full px-4 py-2.5 rounded-xl text-slate-100 glass-input text-sm outline-none font-medium"
                      />
                      <span className="text-[10px] text-slate-500 block font-medium">
                        If dynamic parts creation fails or description is empty, use this item name.
                      </span>
                    </div>
                  </div>

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={isSavingMappings}
                      className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] text-white font-bold text-sm rounded-xl cursor-pointer transition-all duration-200 disabled:opacity-50"
                    >
                      {isSavingMappings ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      Save Mappings
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* Sync Queue Failures / History */}
            {connected && (
              <div className="glass-card rounded-2xl p-6 relative overflow-hidden shadow-xl">
                <h2 className="text-lg font-bold text-slate-200 mb-4 flex items-center gap-2 font-sans">
                  <AlertCircle className="w-5 h-5 text-indigo-400" />
                  Recent Sync Errors ({errorsList.length})
                </h2>

                {errorsList.length === 0 ? (
                  <div className="text-center py-10 border border-dashed border-slate-800/60 rounded-xl bg-slate-900/10">
                    <Check className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                    <span className="text-sm font-bold text-slate-300 block">No Sync Failures</span>
                    <span className="text-xs text-slate-500 font-medium">All paid invoices have been synced successfully!</span>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {errorsList.map((err) => (
                      <div key={err.id} className="p-4 rounded-xl bg-slate-900/40 border border-slate-800 flex flex-col md:flex-row justify-between items-start md:items-center gap-4 hover:border-slate-700/60 transition-colors">
                        <div className="space-y-1.5 flex-1 w-full">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-slate-200">{err.invoice_number}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 font-bold">
                              Failed
                            </span>
                          </div>
                          
                          <div className="text-xs text-slate-400 space-y-1 font-medium">
                            <div className="flex items-center gap-1.5">
                              <Clock className="w-3.5 h-3.5 text-slate-500" />
                              <span>{new Date(err.failed_at).toLocaleString()}</span>
                              <span className="text-slate-600">•</span>
                              <span>Attempts: {err.attempts}</span>
                            </div>
                            <pre className="mt-2 p-2 bg-slate-950 rounded border border-slate-800 text-[10px] text-rose-300 overflow-x-auto whitespace-pre-wrap font-mono max-h-24 leading-normal">
                              {err.error_message}
                            </pre>
                          </div>
                        </div>

                        <button
                          onClick={() => handleRetrySync(err.id, err.invoice_id)}
                          disabled={retryingId !== null}
                          className="flex items-center gap-1.5 px-4 py-2 border border-indigo-500/20 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-300 font-bold text-xs rounded-xl cursor-pointer transition-all duration-200 disabled:opacity-50 self-end md:self-center"
                        >
                          {retryingId === err.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3.5 h-3.5" />
                          )}
                          Retry Sync
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

          </div>

        </div>
      )}
    </div>
  );
}
