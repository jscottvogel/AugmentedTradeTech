"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "../../../../../hooks/useAuth";
import { AuthGuard } from "../../../../../components/AuthGuard";
import {
  ArrowLeft,
  Plus,
  Trash2,
  Edit,
  Loader2,
  Send,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Percent,
  Coins,
  FileText,
  Check,
  X,
  CreditCard,
  Receipt,
  Calendar,
  DollarSign,
  Ban,
  User,
  AlertTriangle
} from "lucide-react";

export default function InvoiceReviewScreen() {
  return (
    <AuthGuard>
      <InvoiceReviewContent />
    </AuthGuard>
  );
}

interface Customer {
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
}

interface Job {
  id: string;
  job_number: string;
  trade: string;
  job_type: string;
  status: string;
  customer: Customer;
}

interface LineItem {
  id: string;
  line_type: string; // labor | part | fee
  description: string;
  quantity: number;
  unit_price_cents: number;
  total_cents: number;
  is_taxable: boolean;
  discount_pct: number;
  discount_reason: string | null;
}

interface Loyalty {
  available_balance: number;
  redeemed_points: number;
  redeemed_cents: number;
}

interface MembershipDiscount {
  applied: boolean;
  labor_discount_pct: number;
  parts_discount_pct: number;
}

interface Invoice {
  id: string;
  job_id: string;
  customer_id: string;
  invoice_number: string;
  status: string; // draft | sent | paid | void
  subtotal_cents: number;
  tax_cents: number;
  discount_cents: number;
  total_cents: number;
  amount_paid_cents: number;
  balance_cents: number;
  tax_rate_bps: number;
  due_date: string | null;
  payment_terms: string;
  notes: string | null;
  sent_at: string | null;
  paid_at: string | null;
  voided_at: string | null;
  line_items: LineItem[];
  loyalty: Loyalty;
  membership: MembershipDiscount;
}

function InvoiceReviewContent() {
  const params = useParams();
  const router = useRouter();
  const { accessToken, user } = useAuth();
  const id = params.id as string; // job_id

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Data State
  const [job, setJob] = useState<Job | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modals
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState<LineItem | null>(null);
  const [showPaymentModal, setShowPaymentModal] = useState(false);

  // Form Fields - Line Item
  const [lineType, setLineType] = useState<string>("labor");
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState<number>(1);
  const [unitPrice, setUnitPrice] = useState<string>("");
  const [isTaxable, setIsTaxable] = useState(true);
  const [discountPct, setDiscountPct] = useState<number>(0);
  const [discountReason, setDiscountReason] = useState("");

  // Form Fields - Loyalty Redemption
  const [redeemInput, setRedeemInput] = useState<string>("");
  const [loyaltyError, setLoyaltyError] = useState<string | null>(null);

  // Form Fields - Notes & Payment Terms
  const [notes, setNotes] = useState("");
  const [paymentTerms, setPaymentTerms] = useState("due_on_receipt");

  // Form Fields - Payment Method
  const [paymentMethod, setPaymentMethod] = useState("card_present");

  const isAdmin = user?.role === "company_admin";
  const isDraft = invoice?.status === "draft";
  const isSent = invoice?.status === "sent";
  const isPaid = invoice?.status === "paid";
  const isVoid = invoice?.status === "void";

  // Fetch job & invoice on mount
  const loadData = async () => {
    if (!accessToken) return;
    try {
      setIsLoading(true);
      setError(null);

      // Fetch Job Details
      const jobRes = await fetch(`${API_URL}/jobs/${id}`, {
        headers: { Authorization: `Bearer ${accessToken}` }
      });
      if (!jobRes.ok) throw new Error("Failed to load job details.");
      const jobData = await jobRes.json();
      setJob(jobData);

      // Fetch or Create Draft Invoice from Job completion data
      const invRes = await fetch(`${API_URL}/invoices/jobs/${id}/invoice/draft`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ redeem_points: 0 })
      });
      if (!invRes.ok) throw new Error("Failed to generate or retrieve draft invoice.");
      const invData = await invRes.json();
      setInvoice(invData);
      setRedeemInput(invData.loyalty.redeemed_points.toString());
      setNotes(invData.notes || "");
      setPaymentTerms(invData.payment_terms || "due_on_receipt");
    } catch (err: any) {
      console.error(err);
      setError(err.message || "An error occurred while loading data.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [id, accessToken]);

  // Sync / Refresh invoice helper
  const updateInvoiceState = (data: Invoice) => {
    setInvoice(data);
    setRedeemInput(data.loyalty.redeemed_points.toString());
    setNotes(data.notes || "");
    setPaymentTerms(data.payment_terms || "due_on_receipt");
    setLoyaltyError(null);
  };

  // 1. Add Line Item
  const handleAddLineItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invoice || isSubmitting) return;
    const priceCents = Math.round(parseFloat(unitPrice) * 100);
    if (isNaN(priceCents) || priceCents < 0) {
      alert("Please enter a valid unit price.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/line-items`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          line_type: lineType,
          description,
          quantity,
          unit_price_cents: priceCents,
          is_taxable: isTaxable,
          discount_pct: discountPct,
          discount_reason: discountReason || null
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to add line item.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      setShowAddModal(false);
      // Reset form
      setLineType("labor");
      setDescription("");
      setQuantity(1);
      setUnitPrice("");
      setIsTaxable(true);
      setDiscountPct(0);
      setDiscountReason("");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 2. Open Edit Modal
  const openEditModal = (item: LineItem) => {
    setSelectedItem(item);
    setLineType(item.line_type);
    setDescription(item.description);
    setQuantity(item.quantity);
    setUnitPrice((item.unit_price_cents / 100).toFixed(2));
    setIsTaxable(item.is_taxable);
    setDiscountPct(item.discount_pct);
    setDiscountReason(item.discount_reason || "");
    setShowEditModal(true);
  };

  // 3. Edit Line Item
  const handleEditLineItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invoice || !selectedItem || isSubmitting) return;
    const priceCents = Math.round(parseFloat(unitPrice) * 100);
    if (isNaN(priceCents) || priceCents < 0) {
      alert("Please enter a valid unit price.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/line-items/${selectedItem.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          line_type: lineType,
          description,
          quantity,
          unit_price_cents: priceCents,
          is_taxable: isTaxable,
          discount_pct: discountPct,
          discount_reason: discountReason || null
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to update line item.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      setShowEditModal(false);
      setSelectedItem(null);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 4. Delete Line Item
  const handleDeleteLineItem = async (lid: string) => {
    if (!invoice || isSubmitting) return;
    if (!confirm("Are you sure you want to remove this line item?")) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/line-items/${lid}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` }
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to delete line item.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 5. Update Loyalty Points
  const handleApplyLoyalty = async () => {
    if (!invoice || isSubmitting) return;
    const pts = parseInt(redeemInput);
    if (isNaN(pts) || pts < 0) {
      setLoyaltyError("Please enter a valid positive integer of points.");
      return;
    }

    const maxAllowed = invoice.loyalty.available_balance + invoice.loyalty.redeemed_points;
    if (pts > maxAllowed) {
      setLoyaltyError(`Insufficient points. Maximum available: ${maxAllowed} points.`);
      return;
    }

    setIsSubmitting(true);
    setLoyaltyError(null);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ redeem_points: pts })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to update loyalty redemption.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
    } catch (err: any) {
      setLoyaltyError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 6. Update Notes & Payment Terms
  const handleUpdateInvoiceTerms = async () => {
    if (!invoice || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          notes,
          payment_terms: paymentTerms
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to update terms.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      alert("Invoice notes and terms saved.");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 7. Send Invoice to Customer
  const handleSendInvoice = async () => {
    if (!invoice || isSubmitting) return;
    if (!confirm("Send this invoice to the customer? This will trigger an SMS and Email notification.")) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/send`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to send invoice.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      alert("Invoice sent successfully via Email and SMS!");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 8. Collect Payment
  const handleCollectPayment = async () => {
    if (!invoice || isSubmitting) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          status: "paid",
          payment_method: paymentMethod
        })
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to process payment.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      setShowPaymentModal(false);
      alert("Payment successfully processed! Invoice is marked as paid.");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 9. Void Invoice (Admin Only)
  const handleVoidInvoice = async () => {
    if (!invoice || isSubmitting) return;
    if (!confirm("Are you sure you want to void this invoice? This cannot be undone and will void any loyalty points redeemed.")) return;

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/void`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` }
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to void invoice.");
      }

      const updated = await res.json();
      updateInvoiceState(updated);
      alert("Invoice has been voided.");
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
          <p className="text-slate-400 text-xs font-semibold">Loading invoice review...</p>
        </div>
      </div>
    );
  }

  if (error || !invoice || !job) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        <AlertCircle className="w-12 h-12 text-red-500 mb-4 animate-pulse" />
        <h3 className="text-white font-extrabold text-base mb-2">Error Loading Invoice</h3>
        <p className="text-slate-400 text-xs max-w-sm mb-6 leading-relaxed">
          {error || "Could not retrieve invoice details."}
        </p>
        <button
          onClick={() => router.push(`/app/jobs/${id}`)}
          className="bg-slate-900 border border-slate-800 text-indigo-400 px-5 py-2.5 rounded-xl font-bold text-xs cursor-pointer hover:bg-slate-850 transition"
        >
          Return to Job details
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white flex justify-center selection:bg-indigo-500 selection:text-white pb-24">
      {/* Mobile container constraint */}
      <main className="w-full max-w-[480px] bg-slate-950/70 min-h-screen border-x border-slate-900/60 flex flex-col pb-16 relative">
        
        {/* Sticky Header */}
        <div className="sticky top-0 bg-slate-950/85 backdrop-blur-md z-30 border-b border-slate-900/60 p-4 flex items-center justify-between">
          <button
            onClick={() => router.push(`/app/jobs/${id}`)}
            className="flex items-center gap-1.5 text-slate-400 hover:text-white border-none bg-transparent font-semibold text-xs cursor-pointer transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Job Order</span>
          </button>
          
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wide">
              Status:
            </span>
            <span className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase border capitalize ${
              isPaid ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" :
              isSent ? "bg-blue-500/10 border-blue-500/20 text-blue-400" :
              isVoid ? "bg-red-500/10 border-red-500/20 text-red-400" :
              "bg-slate-800/50 border-slate-700 text-slate-400"
            }`}>
              {invoice.status}
            </span>
          </div>
        </div>

        {/* Hero Invoice Card */}
        <div className="p-4 flex flex-col gap-4">
          <div className="bg-gradient-to-b from-slate-900/40 to-slate-950/20 border border-slate-900 rounded-2xl p-5 flex flex-col gap-4 shadow-xl relative overflow-hidden">
            <div className="absolute right-0 top-0 w-24 h-24 bg-indigo-500/5 rounded-full blur-2xl pointer-events-none" />
            <div className="flex justify-between items-start">
              <div>
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Invoice #</span>
                <h1 className="text-xl font-black text-white tracking-tight mt-0.5">
                  {invoice.invoice_number === "PENDING" ? "DRAFT (PENDING)" : invoice.invoice_number}
                </h1>
              </div>
              <Receipt className="w-8 h-8 text-indigo-400 opacity-60" />
            </div>

            <div className="border-t border-slate-900 pt-3 flex flex-col gap-1.5">
              <span className="text-[9px] font-bold text-slate-500 uppercase tracking-wider">Customer Info</span>
              <h3 className="text-xs font-bold text-white">
                {job.customer.first_name} {job.customer.last_name}
              </h3>
              <p className="text-[10px] text-slate-400 leading-relaxed">
                {job.customer.address_line1} {job.customer.address_line2 ? `, ${job.customer.address_line2}` : ""}
                <br />
                {job.customer.city}, {job.customer.state} {job.customer.zip}
              </p>
            </div>
          </div>

          {/* Active Membership Badge */}
          {invoice.membership.applied && (
            <div className="glass-card rounded-2xl p-4 border border-indigo-500/20 bg-indigo-950/10 flex items-start gap-3 shadow-md relative overflow-hidden">
              <div className="absolute right-0 top-0 w-12 h-12 bg-indigo-400/5 rounded-full blur-xl pointer-events-none" />
              <Sparkles className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5 animate-pulse" />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold text-indigo-300">Active Membership discounts active</span>
                  <span className="bg-indigo-500/20 text-indigo-300 text-[8px] font-bold px-1.5 py-0.5 rounded border border-indigo-500/20">MEMBERSHIP</span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1 leading-normal">
                  Labor discount: <strong className="text-white">{invoice.membership.labor_discount_pct}%</strong> | Parts discount: <strong className="text-white">{invoice.membership.parts_discount_pct}%</strong>
                </p>
              </div>
            </div>
          )}

          {/* Line Items Header */}
          <div className="flex justify-between items-center mt-2 px-1">
            <h2 className="text-sm font-extrabold text-white tracking-tight flex items-center gap-1.5">
              <FileText className="w-4 h-4 text-indigo-400" />
              <span>Line Items</span>
            </h2>
            {isDraft && (
              <button
                onClick={() => setShowAddModal(true)}
                className="bg-indigo-650 hover:bg-indigo-600 text-white font-bold text-xs py-1.5 px-3 rounded-lg border-none flex items-center gap-1 transition cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Item</span>
              </button>
            )}
          </div>

          {/* Line Items List */}
          <div className="flex flex-col gap-3">
            {invoice.line_items.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500 border border-dashed border-slate-900 rounded-2xl bg-slate-900/5">
                No line items on this invoice. Add items to calculate totals.
              </div>
            ) : (
              invoice.line_items.map((item) => {
                const totalDollars = item.total_cents / 100.0;
                const unitPriceDollars = item.unit_price_cents / 100.0;
                return (
                  <div
                    key={item.id}
                    className="glass-card rounded-2xl p-4 flex flex-col gap-2 relative overflow-hidden group border border-slate-900 bg-slate-950/30"
                  >
                    <div className="flex justify-between items-start gap-2">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className={`text-[8px] font-black uppercase px-1.5 py-0.5 rounded border ${
                            item.line_type === "labor" ? "bg-sky-500/10 border-sky-500/20 text-sky-400" :
                            item.line_type === "part" ? "bg-amber-500/10 border-amber-500/20 text-amber-400" :
                            "bg-slate-800 border-slate-700 text-slate-350"
                          }`}>
                            {item.line_type}
                          </span>
                          {!item.is_taxable && (
                            <span className="text-[8px] text-slate-500 font-bold bg-slate-900 border border-slate-850 px-1 py-0.2 rounded">
                              Non-Taxable
                            </span>
                          )}
                        </div>
                        <h4 className="text-xs font-bold text-slate-100 mt-1 leading-snug">
                          {item.description}
                        </h4>
                      </div>
                      
                      <div className="text-right shrink-0">
                        <span className="text-xs font-black text-white">
                          ${totalDollars.toFixed(2)}
                        </span>
                        <div className="text-[9px] text-slate-500 mt-0.5 font-medium">
                          {item.quantity} × ${unitPriceDollars.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    {/* Applied Line Item Discounts */}
                    {item.discount_pct > 0 && (
                      <div className="bg-slate-900/60 border border-slate-900 p-2 rounded-xl flex items-center justify-between text-[9px] mt-1">
                        <div className="flex items-center gap-1.5 text-indigo-400 font-semibold">
                          <Percent className="w-3 h-3" />
                          <span>Discount Applied:</span>
                          <span className="text-white font-bold">{item.discount_pct}% Off</span>
                        </div>
                        {item.discount_reason && (
                          <span className="text-slate-500 italic max-w-[200px] truncate">
                            "{item.discount_reason}"
                          </span>
                        )}
                      </div>
                    )}

                    {/* Action buttons inside Card */}
                    {isDraft && (
                      <div className="flex gap-2 justify-end border-t border-slate-900/80 pt-2.5 mt-1.5 opacity-80 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => openEditModal(item)}
                          className="bg-transparent border-none text-slate-400 hover:text-white flex items-center gap-1 text-[10px] font-bold cursor-pointer transition"
                        >
                          <Edit className="w-3 h-3" />
                          <span>Edit</span>
                        </button>
                        <span className="text-slate-800">|</span>
                        <button
                          onClick={() => handleDeleteLineItem(item.id)}
                          className="bg-transparent border-none text-red-400 hover:text-red-300 flex items-center gap-1 text-[10px] font-bold cursor-pointer transition"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Delete</span>
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* Loyalty Points Section */}
          <div className="bg-slate-900/10 border border-slate-900 rounded-2xl p-4.5 flex flex-col gap-3 shadow-inner">
            <h3 className="text-xs font-black text-white tracking-wide uppercase flex items-center gap-1.5">
              <Coins className="w-4 h-4 text-amber-400" />
              <span>Loyalty Points Rewards</span>
            </h3>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 font-medium">Customer Balance Available:</span>
              <span className="text-amber-400 font-bold bg-amber-500/10 px-2 py-0.5 rounded-lg border border-amber-500/10">
                {invoice.loyalty.available_balance + invoice.loyalty.redeemed_points} points (${((invoice.loyalty.available_balance + invoice.loyalty.redeemed_points) * 0.01).toFixed(2)})
              </span>
            </div>

            {isDraft ? (
              <div className="flex flex-col gap-2 mt-1">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">
                  Redeem Points (1 point = $0.01)
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={redeemInput}
                    onChange={(e) => setRedeemInput(e.target.value)}
                    placeholder="Enter points to redeem..."
                    disabled={isSubmitting}
                    className="flex-1 bg-slate-900 border border-slate-800 text-white rounded-xl px-3 py-2 text-xs placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 glass-input"
                  />
                  <button
                    onClick={handleApplyLoyalty}
                    disabled={isSubmitting}
                    className="bg-indigo-650 hover:bg-indigo-600 text-white font-bold text-xs px-4 rounded-xl transition cursor-pointer border-none flex items-center justify-center gap-1.5 whitespace-nowrap"
                  >
                    {isSubmitting ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <span>Apply</span>
                    )}
                  </button>
                </div>
                {loyaltyError && (
                  <p className="text-[10px] text-red-400 flex items-center gap-1 font-semibold">
                    <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>{loyaltyError}</span>
                  </p>
                )}
              </div>
            ) : invoice.loyalty.redeemed_points > 0 ? (
              <div className="bg-slate-900 border border-slate-850 p-3 rounded-xl flex items-center justify-between text-xs mt-1">
                <span className="text-slate-400">Redeemed on this invoice:</span>
                <span className="text-white font-black">{invoice.loyalty.redeemed_points} points (-${(invoice.loyalty.redeemed_cents / 100).toFixed(2)})</span>
              </div>
            ) : null}
          </div>

          {/* Payment Terms & Notes */}
          <div className="bg-slate-900/10 border border-slate-900 rounded-2xl p-4.5 flex flex-col gap-4">
            <h3 className="text-xs font-black text-white tracking-wide uppercase flex items-center gap-1.5">
              <Calendar className="w-4 h-4 text-indigo-400" />
              <span>Notes & Terms</span>
            </h3>

            {isDraft ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Payment Terms
                  </label>
                  <select
                    value={paymentTerms}
                    onChange={(e) => setPaymentTerms(e.target.value)}
                    disabled={isSubmitting}
                    className="bg-slate-900 border border-slate-800 text-white text-xs rounded-xl p-2.5 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="due_on_receipt">Due on Receipt</option>
                    <option value="net_15">Net 15 Days</option>
                    <option value="net_30">Net 30 Days</option>
                    <option value="net_60">Net 60 Days</option>
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Invoice Notes (shown to customer)
                  </label>
                  <textarea
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Enter invoice notes, e.g. warranty coverage details..."
                    disabled={isSubmitting}
                    className="bg-slate-900 border border-slate-800 text-white text-xs rounded-xl p-2.5 focus:outline-none focus:border-indigo-500 placeholder:text-slate-650"
                  />
                </div>

                <button
                  onClick={handleUpdateInvoiceTerms}
                  disabled={isSubmitting}
                  className="bg-slate-900 border border-slate-800 hover:bg-slate-850 text-indigo-400 font-bold text-xs py-2 rounded-xl transition cursor-pointer"
                >
                  Save Notes & Terms
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2 text-xs">
                <div className="flex justify-between border-b border-slate-900 pb-2">
                  <span className="text-slate-400">Payment Terms:</span>
                  <span className="text-white font-bold capitalize">
                    {invoice.payment_terms.replace(/_/g, " ")}
                  </span>
                </div>
                {invoice.notes && (
                  <div className="flex flex-col gap-1 pt-1">
                    <span className="text-slate-400">Invoice Notes:</span>
                    <p className="bg-slate-950/30 p-2.5 border border-slate-900 rounded-xl text-[11px] text-slate-350 italic">
                      "{invoice.notes}"
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Pricing Summary Card */}
          <div className="glass-card rounded-2xl p-5 border border-slate-900 bg-slate-900/15 flex flex-col gap-3 shadow-xl">
            <h3 className="text-xs font-black text-white tracking-wide uppercase border-b border-slate-900 pb-2 flex items-center gap-1.5">
              <DollarSign className="w-4 h-4 text-emerald-400" />
              <span>Invoice Pricing Summary</span>
            </h3>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 font-medium">Subtotal:</span>
              <span className="text-white font-bold">
                ${(invoice.subtotal_cents / 100).toFixed(2)}
              </span>
            </div>

            {invoice.discount_cents > 0 && (
              <div className="flex justify-between items-center text-xs text-indigo-400">
                <span className="font-medium flex items-center gap-1">
                  <Percent className="w-3.5 h-3.5" />
                  Total Discounts:
                </span>
                <span className="font-black">
                  -${(invoice.discount_cents / 100).toFixed(2)}
                </span>
              </div>
            )}

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 font-medium">
                Sales Tax ({(invoice.tax_rate_bps / 100).toFixed(2)}%):
              </span>
              <span className="text-white font-bold">
                ${(invoice.tax_cents / 100).toFixed(2)}
              </span>
            </div>

            <div className="border-t border-slate-900 pt-3 flex justify-between items-center mt-1">
              <span className="text-sm font-black text-white uppercase tracking-wider">Total:</span>
              <span className="text-xl font-black text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.15)]">
                ${(invoice.total_cents / 100).toFixed(2)}
              </span>
            </div>

            {isPaid && (
              <div className="bg-emerald-500/10 border border-emerald-500/20 p-3.5 rounded-xl flex flex-col gap-1 text-xs mt-2">
                <div className="flex justify-between items-center">
                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-4.5 h-4.5" />
                    Paid In Full:
                  </span>
                  <span className="text-white font-black">
                    ${(invoice.amount_paid_cents / 100).toFixed(2)}
                  </span>
                </div>
                {invoice.paid_at && (
                  <p className="text-[10px] text-slate-400 mt-1 font-semibold text-right">
                    Processed at: {new Date(invoice.paid_at).toLocaleDateString()} {new Date(invoice.paid_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Primary Action Buttons (Invoiced state/actions) */}
          <div className="flex flex-col gap-2 mt-4">
            {isDraft && (
              <>
                <button
                  onClick={handleSendInvoice}
                  disabled={isSubmitting || invoice.line_items.length === 0}
                  className="w-full py-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 text-white border-none shadow-lg transition duration-200 cursor-pointer bg-gradient-to-r from-indigo-500 to-indigo-650 hover:from-indigo-650 hover:to-indigo-700 shadow-indigo-500/25 disabled:opacity-40 disabled:pointer-events-none"
                >
                  <Send className="w-4 h-4 animate-pulse" />
                  <span>Send to Customer (SMS + Email)</span>
                </button>

                <button
                  onClick={() => router.push(`/app/jobs/${id}/invoice/pay`)}
                  disabled={isSubmitting || invoice.line_items.length === 0}
                  className="w-full py-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 text-white border-none shadow-lg transition duration-200 cursor-pointer bg-gradient-to-r from-emerald-500 to-emerald-650 hover:from-emerald-650 hover:to-emerald-700 shadow-emerald-500/25 disabled:opacity-40 disabled:pointer-events-none"
                >
                  <CreditCard className="w-4 h-4" />
                  <span>Collect Payment</span>
                </button>
              </>
            )}

            {isSent && (
              <div className="flex flex-col gap-2">
                <div className="bg-blue-500/10 border border-blue-500/20 p-3 rounded-xl flex items-center gap-2 text-xs mb-1">
                  <AlertTriangle className="w-4 h-4 text-blue-450 shrink-0" />
                  <span className="text-slate-300">Invoice was sent. Waiting for customer payment or collect now below.</span>
                </div>
                
                <button
                  onClick={() => router.push(`/app/jobs/${id}/invoice/pay`)}
                  disabled={isSubmitting}
                  className="w-full py-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 text-white border-none shadow-lg transition duration-200 cursor-pointer bg-gradient-to-r from-emerald-500 to-emerald-650 hover:from-emerald-650 hover:to-emerald-700 shadow-emerald-500/25"
                >
                  <CreditCard className="w-4 h-4" />
                  <span>Collect Payment Now</span>
                </button>

                <button
                  onClick={handleSendInvoice}
                  disabled={isSubmitting}
                  className="w-full py-2.5 rounded-xl font-bold text-xs bg-slate-900 border border-slate-800 text-indigo-400 hover:bg-slate-850 transition cursor-pointer"
                >
                  Resend Invoice Link
                </button>
              </div>
            )}

            {isPaid && (
              <div className="bg-emerald-500/15 border border-emerald-500/25 rounded-2xl p-4 text-center font-bold text-xs text-emerald-300 shadow-lg flex flex-col items-center gap-2">
                <CheckCircle2 className="w-10 h-10 text-emerald-400 animate-bounce" />
                <span>Invoice Paid & Processed successfully</span>
                <p className="text-[10px] text-slate-400 font-semibold">The job card has automatically been moved to Paid status.</p>
              </div>
            )}

            {isVoid && (
              <div className="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 text-center font-bold text-xs text-red-400 shadow-md flex items-center justify-center gap-2">
                <Ban className="w-5 h-5" />
                <span>This invoice has been voided.</span>
              </div>
            )}

            {/* Admin-only Void CTA */}
            {isAdmin && !isVoid && !isPaid && (
              <button
                onClick={handleVoidInvoice}
                disabled={isSubmitting}
                className="w-full py-2.5 rounded-xl font-bold text-xs bg-red-500/10 border border-red-500/25 text-red-450 hover:bg-red-500/20 transition cursor-pointer mt-4"
              >
                Void Invoice (Admin Only)
              </button>
            )}
          </div>
        </div>

        {/* MODAL: Add Line Item */}
        {showAddModal && (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <form
              onSubmit={handleAddLineItem}
              className="w-full max-w-[400px] bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col gap-4 animate-scaleUp text-xs"
            >
              <div className="flex justify-between items-center border-b border-slate-850 pb-3">
                <h3 className="text-sm font-black text-white flex items-center gap-1.5">
                  <Plus className="w-4.5 h-4.5 text-indigo-400" />
                  <span>Add Line Item</span>
                </h3>
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="bg-transparent border-none text-slate-500 hover:text-white cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Line Type Selection */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                  Type
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {["labor", "part", "fee"].map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setLineType(type)}
                      className={`py-2 rounded-xl font-bold text-[10px] capitalize transition cursor-pointer border ${
                        lineType === type
                          ? "bg-indigo-500/15 border-indigo-500 text-indigo-300"
                          : "bg-slate-950/50 border-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                  Description
                </label>
                <input
                  type="text"
                  required
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. Capacitor replacement..."
                  className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 placeholder:text-slate-700"
                />
              </div>

              {/* Quantity and Unit Price */}
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Quantity
                  </label>
                  <input
                    type="number"
                    step="any"
                    required
                    min="0.01"
                    value={quantity}
                    onChange={(e) => setQuantity(parseFloat(e.target.value))}
                    className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Unit Price ($)
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-500">$</span>
                    <input
                      type="number"
                      step="0.01"
                      required
                      min="0"
                      value={unitPrice}
                      onChange={(e) => setUnitPrice(e.target.value)}
                      placeholder="0.00"
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl pl-6 pr-3 py-2.5 w-full focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Taxable Toggle */}
              <div className="flex justify-between items-center py-1">
                <div className="flex flex-col">
                  <span className="font-bold text-slate-300">Is Taxable</span>
                  <span className="text-[9px] text-slate-500 mt-0.5">Apply standard sales tax to this item</span>
                </div>
                <input
                  type="checkbox"
                  checked={isTaxable}
                  onChange={(e) => setIsTaxable(e.target.checked)}
                  className="w-4 h-4 accent-indigo-500 cursor-pointer"
                />
              </div>

              {/* Discount Section */}
              <div className="border-t border-slate-850 pt-3 flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                      Item Discount (%)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={discountPct}
                      onChange={(e) => setDiscountPct(parseFloat(e.target.value) || 0)}
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                      Discount Reason
                    </label>
                    <input
                      type="text"
                      value={discountReason}
                      onChange={(e) => setDiscountReason(e.target.value)}
                      placeholder="e.g. Loyalty rate..."
                      disabled={discountPct === 0}
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 placeholder:text-slate-700 disabled:opacity-40"
                    />
                  </div>
                </div>
              </div>

              <div className="flex gap-2 justify-end border-t border-slate-850 pt-4 mt-1">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="bg-slate-950 border border-slate-800 hover:bg-slate-850 text-slate-400 py-2.5 px-4 rounded-xl font-bold cursor-pointer transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-indigo-650 hover:bg-indigo-600 text-white py-2.5 px-5 rounded-xl font-bold cursor-pointer transition flex items-center gap-1.5 border-none"
                >
                  {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Add Item</span>
                </button>
              </div>
            </form>
          </div>
        )}

        {/* MODAL: Edit Line Item */}
        {showEditModal && selectedItem && (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <form
              onSubmit={handleEditLineItem}
              className="w-full max-w-[400px] bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col gap-4 animate-scaleUp text-xs"
            >
              <div className="flex justify-between items-center border-b border-slate-850 pb-3">
                <h3 className="text-sm font-black text-white flex items-center gap-1.5">
                  <Edit className="w-4.5 h-4.5 text-indigo-400" />
                  <span>Edit Line Item</span>
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setShowEditModal(false);
                    setSelectedItem(null);
                  }}
                  className="bg-transparent border-none text-slate-500 hover:text-white cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Line Type Selection */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                  Type
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {["labor", "part", "fee"].map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => setLineType(type)}
                      className={`py-2 rounded-xl font-bold text-[10px] capitalize transition cursor-pointer border ${
                        lineType === type
                          ? "bg-indigo-500/15 border-indigo-500 text-indigo-300"
                          : "bg-slate-950/50 border-slate-800 text-slate-400 hover:text-white"
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {/* Description */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                  Description
                </label>
                <input
                  type="text"
                  required
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. Capacitor replacement..."
                  className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500"
                />
              </div>

              {/* Quantity and Unit Price */}
              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Quantity
                  </label>
                  <input
                    type="number"
                    step="any"
                    required
                    min="0.01"
                    value={quantity}
                    onChange={(e) => setQuantity(parseFloat(e.target.value))}
                    className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                    Unit Price ($)
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-2.5 text-slate-500">$</span>
                    <input
                      type="number"
                      step="0.01"
                      required
                      min="0"
                      value={unitPrice}
                      onChange={(e) => setUnitPrice(e.target.value)}
                      placeholder="0.00"
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl pl-6 pr-3 py-2.5 w-full focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Taxable Toggle */}
              <div className="flex justify-between items-center py-1">
                <div className="flex flex-col">
                  <span className="font-bold text-slate-300">Is Taxable</span>
                  <span className="text-[9px] text-slate-500 mt-0.5">Apply standard sales tax to this item</span>
                </div>
                <input
                  type="checkbox"
                  checked={isTaxable}
                  onChange={(e) => setIsTaxable(e.target.checked)}
                  className="w-4 h-4 accent-indigo-500 cursor-pointer"
                />
              </div>

              {/* Discount Section */}
              <div className="border-t border-slate-850 pt-3 flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                      Item Discount (%)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={discountPct}
                      onChange={(e) => setDiscountPct(parseFloat(e.target.value) || 0)}
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                      Discount Reason
                    </label>
                    <input
                      type="text"
                      value={discountReason}
                      onChange={(e) => setDiscountReason(e.target.value)}
                      placeholder="e.g. Loyalty rate..."
                      disabled={discountPct === 0}
                      className="bg-slate-950 border border-slate-800 text-white rounded-xl px-3 py-2.5 focus:outline-none focus:border-indigo-500 placeholder:text-slate-700 disabled:opacity-40"
                    />
                  </div>
                </div>
              </div>

              <div className="flex gap-2 justify-end border-t border-slate-850 pt-4 mt-1">
                <button
                  type="button"
                  onClick={() => {
                    setShowEditModal(false);
                    setSelectedItem(null);
                  }}
                  className="bg-slate-950 border border-slate-800 hover:bg-slate-850 text-slate-400 py-2.5 px-4 rounded-xl font-bold cursor-pointer transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-indigo-650 hover:bg-indigo-600 text-white py-2.5 px-5 rounded-xl font-bold cursor-pointer transition flex items-center gap-1.5 border-none"
                >
                  {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Save Changes</span>
                </button>
              </div>
            </form>
          </div>
        )}

        {/* MODAL: Collect Payment Method selection */}
        {showPaymentModal && (
          <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-[380px] bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col gap-4 animate-scaleUp text-xs">
              <div className="flex justify-between items-center border-b border-slate-850 pb-3">
                <h3 className="text-sm font-black text-white flex items-center gap-1.5">
                  <CreditCard className="w-4.5 h-4.5 text-emerald-450" />
                  <span>Collect Payment</span>
                </h3>
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className="bg-transparent border-none text-slate-500 hover:text-white cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex flex-col gap-1 text-center py-2 bg-slate-950/40 rounded-2xl border border-slate-950 p-4">
                <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Amount Due</span>
                <span className="text-2xl font-black text-emerald-400">${(invoice.total_cents / 100).toFixed(2)}</span>
              </div>

              <div className="flex flex-col gap-2 mt-1">
                <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">
                  Select Payment Method
                </label>
                <div className="flex flex-col gap-2">
                  {[
                    { id: "card_present", label: "Swipe / Dip / Tap (Card Reader)", icon: <CreditCard className="w-4 h-4" /> },
                    { id: "card_on_file", label: "Use Customer Card on File", icon: <User className="w-4 h-4" /> },
                    { id: "cash", label: "Cash", icon: <DollarSign className="w-4 h-4" /> },
                    { id: "check", label: "Check", icon: <Receipt className="w-4 h-4" /> }
                  ].map((method) => (
                    <button
                      key={method.id}
                      type="button"
                      onClick={() => setPaymentMethod(method.id)}
                      className={`flex items-center gap-3 p-3 rounded-2xl border font-bold text-left cursor-pointer transition ${
                        paymentMethod === method.id
                          ? "bg-emerald-500/10 border-emerald-500 text-emerald-300 shadow-lg shadow-emerald-500/5"
                          : "bg-slate-950/40 border-slate-800 text-slate-400 hover:text-white hover:border-slate-700"
                      }`}
                    >
                      {method.icon}
                      <span className="text-[11px]">{method.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-2 justify-end border-t border-slate-850 pt-4 mt-3">
                <button
                  type="button"
                  onClick={() => setShowPaymentModal(false)}
                  className="bg-slate-950 border border-slate-800 hover:bg-slate-850 text-slate-400 py-2.5 px-4 rounded-xl font-bold cursor-pointer transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCollectPayment}
                  disabled={isSubmitting}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white py-2.5 px-5 rounded-xl font-bold cursor-pointer transition flex items-center gap-1.5 border-none"
                >
                  {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Record Payment</span>
                </button>
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  );
}
