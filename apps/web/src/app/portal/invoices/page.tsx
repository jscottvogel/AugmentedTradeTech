"use client";

import React, { useState, useEffect } from "react";
import { 
  FileText, 
  CreditCard, 
  Calendar, 
  ChevronRight, 
  X, 
  CheckCircle, 
  AlertCircle, 
  Loader2, 
  ArrowRight 
} from "lucide-react";
import { usePortalAuth } from "../../../context/PortalAuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Invoice {
  id: string;
  invoice_number: string;
  status: string;
  subtotal_cents: number;
  tax_cents: number;
  discount_cents: number;
  total_cents: number;
  amount_paid_cents: number;
  balance_cents: number;
  due_date: string | null;
  payment_terms: string;
  paid_at: string | null;
}

interface LineItem {
  id: string;
  line_type: string;
  description: string;
  quantity: number;
  unit_price_cents: number;
  total_cents: number;
  is_taxable: boolean;
  discount_pct: number;
  discount_reason: string | null;
}

interface InvoiceDetail extends Invoice {
  tax_rate_bps: number;
  notes: string | null;
  customer_signature_url: string | null;
  signed_at: string | null;
  line_items: LineItem[];
}

export default function PortalInvoicesPage() {
  const { accessToken } = usePortalAuth();
  
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"outstanding" | "paid">("outstanding");
  
  // Modal state
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [invoiceDetail, setInvoiceDetail] = useState<InvoiceDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [paying, setPaying] = useState(false);
  const [paySuccess, setPaySuccess] = useState(false);

  // Fetch invoices list
  const fetchInvoices = async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_URL}/portal/invoices`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setInvoices(data);
      }
    } catch (err) {
      console.error("Failed to fetch invoices", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
  }, [accessToken]);

  // Fetch invoice detail
  useEffect(() => {
    if (!selectedInvoiceId || !accessToken) {
      setInvoiceDetail(null);
      setPaySuccess(false);
      return;
    }

    const fetchInvoiceDetail = async () => {
      setLoadingDetail(true);
      try {
        const res = await fetch(`${API_URL}/portal/invoices/${selectedInvoiceId}`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          const data = await res.json();
          setInvoiceDetail(data);
        }
      } catch (err) {
        console.error("Failed to fetch invoice details", err);
      } finally {
        setLoadingDetail(false);
      }
    };

    fetchInvoiceDetail();
  }, [selectedInvoiceId, accessToken]);

  const handlePay = async () => {
    if (!selectedInvoiceId || !accessToken) return;
    
    setPaying(true);
    try {
      const res = await fetch(`${API_URL}/portal/invoices/${selectedInvoiceId}/pay`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}` 
        },
        body: JSON.stringify({ confirm_mock: true })
      });

      if (res.ok) {
        setPaySuccess(true);
        // Refresh invoice list and detail state
        await fetchInvoices();
        
        // Update local detail state to show paid
        if (invoiceDetail) {
          setInvoiceDetail({
            ...invoiceDetail,
            status: "paid",
            balance_cents: 0,
            amount_paid_cents: invoiceDetail.total_cents,
            paid_at: new Date().toISOString()
          });
        }
      } else {
        const errorData = await res.json();
        alert(errorData.detail || "Payment processing failed");
      }
    } catch (err) {
      console.error("Error submitting payment", err);
      alert("An error occurred during payment processing");
    } finally {
      setPaying(false);
    }
  };

  const outstandingInvoices = invoices.filter(inv => inv.status !== "paid");
  const paidInvoices = invoices.filter(inv => inv.status === "paid");
  const currentList = activeTab === "outstanding" ? outstandingInvoices : paidInvoices;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Billing & Invoices</h1>
        <p className="text-slate-400 text-sm">View open balances, receipt details, and submit secure payments.</p>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-white/5 space-x-6">
        <button
          onClick={() => setActiveTab("outstanding")}
          className={`pb-3 font-semibold text-sm transition-all border-b-2 cursor-pointer ${
            activeTab === "outstanding" 
              ? "border-[var(--primary-color)] text-white" 
              : "border-transparent text-slate-400 hover:text-white"
          }`}
        >
          Outstanding ({outstandingInvoices.length})
        </button>
        <button
          onClick={() => setActiveTab("paid")}
          className={`pb-3 font-semibold text-sm transition-all border-b-2 cursor-pointer ${
            activeTab === "paid" 
              ? "border-[var(--primary-color)] text-white" 
              : "border-transparent text-slate-400 hover:text-white"
          }`}
        >
          Paid History ({paidInvoices.length})
        </button>
      </div>

      {/* Invoice List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
        </div>
      ) : currentList.length === 0 ? (
        <div className="p-12 rounded-2xl glass-card border border-white/5 text-center text-slate-500">
          No {activeTab} invoices found.
        </div>
      ) : (
        <div className="grid gap-4">
          {currentList.map(inv => (
            <div 
              key={inv.id} 
              onClick={() => setSelectedInvoiceId(inv.id)}
              className="p-5 rounded-xl glass-card border border-white/5 flex items-center justify-between hover:border-white/10 hover:bg-white/[0.01] transition-all cursor-pointer group"
            >
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-lg bg-[var(--primary-color)]/10 flex items-center justify-center text-[var(--primary-color)]">
                  <FileText className="h-5 w-5" />
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-bold text-slate-400">Invoice #{inv.invoice_number}</span>
                  <h3 className="text-base font-bold text-white">
                    ${(inv.total_cents / 100).toFixed(2)}
                  </h3>
                  {inv.due_date && inv.status !== "paid" && (
                    <p className="text-xs text-amber-400 flex items-center gap-1.5">
                      <Calendar className="h-3.5 w-3.5 text-amber-500" />
                      Due Date: {new Date(inv.due_date).toLocaleDateString()}
                    </p>
                  )}
                  {inv.paid_at && (
                    <p className="text-xs text-emerald-400 flex items-center gap-1.5">
                      <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                      Paid: {new Date(inv.paid_at).toLocaleDateString()}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4">
                <span className={`text-xs font-bold px-2.5 py-1 rounded-lg ${
                  inv.status === "paid" 
                    ? "bg-emerald-500/10 text-emerald-400" 
                    : "bg-amber-500/10 text-amber-400"
                } capitalize`}>
                  {inv.status}
                </span>
                <ChevronRight className="h-5 w-5 text-slate-500 group-hover:text-white transition-colors" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Invoice Detail Modal */}
      {selectedInvoiceId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-3xl bg-gray-900 border border-white/10 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
            
            {/* Modal Header */}
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-white">
                  {loadingDetail ? "Loading..." : `Invoice Details`}
                </h3>
                <p className="text-xs text-slate-400">
                  {!loadingDetail && invoiceDetail && `No. #${invoiceDetail.invoice_number}`}
                </p>
              </div>
              <button 
                onClick={() => setSelectedInvoiceId(null)}
                className="p-1.5 rounded-lg border border-white/5 hover:border-white/20 text-slate-400 hover:text-white transition-all cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-6 flex-grow">
              {loadingDetail ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-[var(--primary-color)]" />
                </div>
              ) : invoiceDetail ? (
                <>
                  {/* Status Banner */}
                  {paySuccess && (
                    <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center gap-3 text-emerald-400">
                      <CheckCircle className="h-5 w-5 shrink-0" />
                      <div>
                        <p className="text-sm font-bold">Payment Completed Successfully!</p>
                        <p className="text-xs text-emerald-500">Thank you for your business. Your receipt details are updated below.</p>
                      </div>
                    </div>
                  )}

                  {/* Summary Details */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 text-sm">
                    <div>
                      <p className="text-xs text-slate-500">Billing Terms</p>
                      <p className="font-semibold text-white mt-0.5">{invoiceDetail.payment_terms}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Due Date</p>
                      <p className="font-semibold text-white mt-0.5">
                        {invoiceDetail.due_date ? new Date(invoiceDetail.due_date).toLocaleDateString() : "Upon Receipt"}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">Status</p>
                      <p className={`font-semibold mt-0.5 capitalize ${
                        invoiceDetail.status === "paid" ? "text-emerald-400" : "text-amber-400"
                      }`}>{invoiceDetail.status}</p>
                    </div>
                  </div>

                  {/* Line Items Table */}
                  <div className="space-y-3">
                    <h4 className="text-sm font-bold text-slate-300">Invoice Items</h4>
                    <div className="border border-white/5 rounded-xl overflow-hidden">
                      <table className="w-full text-left border-collapse text-sm">
                        <thead>
                          <tr className="border-b border-white/5 bg-white/[0.01]">
                            <th className="p-3 font-semibold text-slate-400">Description</th>
                            <th className="p-3 font-semibold text-slate-400 text-center">Qty</th>
                            <th className="p-3 font-semibold text-slate-400 text-right">Rate</th>
                            <th className="p-3 font-semibold text-slate-400 text-right">Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {invoiceDetail.line_items.map((item, index) => (
                            <tr key={item.id || index} className="border-b border-white/5 last:border-b-0 hover:bg-white/[0.005]">
                              <td className="p-3">
                                <p className="font-medium text-white">{item.description}</p>
                                {item.discount_pct > 0 && (
                                  <p className="text-[10px] text-emerald-400 font-semibold mt-0.5">
                                    Member Discount (-{item.discount_pct}%): {item.discount_reason || "Plan applied"}
                                  </p>
                                )}
                              </td>
                              <td className="p-3 text-center text-slate-350">{item.quantity}</td>
                              <td className="p-3 text-right text-slate-350">
                                ${(item.unit_price_cents / 100).toFixed(2)}
                              </td>
                              <td className="p-3 text-right text-white font-medium">
                                ${(item.total_cents / 100).toFixed(2)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Totals Summary */}
                  <div className="flex justify-end">
                    <div className="w-full sm:w-64 space-y-2.5 text-sm p-4 rounded-xl border border-white/5 bg-white/[0.01]">
                      <div className="flex justify-between text-slate-400">
                        <span>Subtotal:</span>
                        <span>${(invoiceDetail.subtotal_cents / 100).toFixed(2)}</span>
                      </div>
                      {invoiceDetail.discount_cents > 0 && (
                        <div className="flex justify-between text-emerald-400">
                          <span>Total Discount:</span>
                          <span>-${(invoiceDetail.discount_cents / 100).toFixed(2)}</span>
                        </div>
                      )}
                      <div className="flex justify-between text-slate-400 border-b border-white/5 pb-2">
                        <span>Tax:</span>
                        <span>${(invoiceDetail.tax_cents / 100).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-white font-bold text-base">
                        <span>Total Due:</span>
                        <span>${(invoiceDetail.total_cents / 100).toFixed(2)}</span>
                      </div>
                      {invoiceDetail.amount_paid_cents > 0 && (
                        <div className="flex justify-between text-slate-400 text-xs">
                          <span>Amount Paid:</span>
                          <span>${(invoiceDetail.amount_paid_cents / 100).toFixed(2)}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Notes */}
                  {invoiceDetail.notes && (
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Payment Notes</h4>
                      <p className="text-xs text-slate-400 italic leading-relaxed">{invoiceDetail.notes}</p>
                    </div>
                  )}

                  {/* Signature Section */}
                  {invoiceDetail.customer_signature_url && (
                    <div className="space-y-2 p-4 rounded-xl border border-white/5 bg-slate-900">
                      <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Customer Authorization</h4>
                      <div className="flex items-center gap-4 mt-2">
                        <img 
                          src={invoiceDetail.customer_signature_url} 
                          alt="Customer Signature" 
                          className="h-10 w-auto bg-white rounded p-1"
                        />
                        <div className="text-xs">
                          <p className="text-white font-medium">Signed Digitally</p>
                          {invoiceDetail.signed_at && (
                            <p className="text-slate-500 mt-0.5">
                              Authorized on {new Date(invoiceDetail.signed_at).toLocaleString()}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="text-center text-slate-500 text-sm">Failed to load invoice details.</p>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-white/5 bg-gray-900/60 flex items-center justify-between gap-4">
              <button 
                onClick={() => setSelectedInvoiceId(null)}
                className="px-5 py-2.5 rounded-xl border border-white/5 hover:border-white/20 text-slate-350 hover:text-white font-semibold text-sm transition-all cursor-pointer"
              >
                Close
              </button>

              {!loadingDetail && invoiceDetail && invoiceDetail.status !== "paid" && (
                <button
                  onClick={handlePay}
                  disabled={paying}
                  className="px-6 py-2.5 rounded-xl text-white font-bold text-sm hover:opacity-95 active:scale-[0.99] transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
                  style={{ backgroundColor: "var(--primary-color)" }}
                >
                  {paying ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Processing Payment...
                    </>
                  ) : (
                    <>
                      <CreditCard className="h-4 w-4" />
                      Pay ${(invoiceDetail.balance_cents / 100).toFixed(2)}
                    </>
                  )}
                </button>
              )}
            </div>
            
          </div>
        </div>
      )}
    </div>
  );
}
