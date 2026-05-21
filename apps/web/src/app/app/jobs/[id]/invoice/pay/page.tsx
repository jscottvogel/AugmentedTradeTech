"use client";

import React, { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../../../../../../hooks/useAuth";
import { AuthGuard } from "../../../../../../components/AuthGuard";
import {
  ArrowLeft,
  Loader2,
  CheckCircle2,
  AlertCircle,
  CreditCard,
  Receipt,
  DollarSign,
  Send,
  Sparkles,
  FileText,
  User,
  Info
} from "lucide-react";

export default function InvoicePaymentScreen() {
  return (
    <AuthGuard>
      <InvoicePaymentContent />
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
  city: string;
  state: string;
  zip: string;
}

interface LineItem {
  id: string;
  line_type: string;
  description: string;
  quantity: number;
  unit_price_cents: number;
  total_cents: number;
}

interface Invoice {
  id: string;
  company_id: string;
  job_id: string;
  customer_id: string;
  invoice_number: string;
  status: string;
  total_cents: number;
  subtotal_cents: number;
  tax_cents: number;
  discount_cents: number;
  line_items: LineItem[];
}

function InvoicePaymentContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();
  
  const id = params.id as string; // job_id
  const isMockPaymentLink = searchParams.get("mock_payment_link") === "true";
  const targetInvoiceId = searchParams.get("invoice_id");

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // State
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Workflow steps: 'signature' | 'payment_select' | 'polling' | 'card_present_simulate' | 'success'
  const [step, setStep] = useState<"signature" | "payment_select" | "polling" | "card_present_simulate" | "success">("signature");
  const [selectedMethod, setSelectedMethod] = useState<"card_present" | "link" | "cash" | "check">("card_present");
  const [paymentLinkUrl, setPaymentLinkUrl] = useState<string | null>(null);
  const [mockClientSecret, setMockClientSecret] = useState<string | null>(null);
  const [mockPaymentIntentId, setMockPaymentIntentId] = useState<string | null>(null);
  const [manualNotes, setManualNotes] = useState("");

  // Canvas Refs
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const isDrawingRef = useRef(false);
  const lastXRef = useRef(0);
  const lastYRef = useRef(0);
  const hasDrawnRef = useRef(false);

  // Confetti Canvas Ref
  const confettiCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // Load Initial Data
  useEffect(() => {
    if (!accessToken) return;

    const loadData = async () => {
      try {
        setIsLoading(true);
        setError(null);

        let currentInvoice: Invoice;
        let jobCustomer: Customer;

        // If it's a customer-facing mock payment link, we fetch the invoice directly
        if (isMockPaymentLink && targetInvoiceId) {
          const invRes = await fetch(`${API_URL}/invoices/${targetInvoiceId}`, {
            headers: { Authorization: `Bearer ${accessToken}` }
          });
          if (!invRes.ok) throw new Error("Failed to load invoice.");
          currentInvoice = await invRes.json();
          setInvoice(currentInvoice);

          const jobRes = await fetch(`${API_URL}/jobs/${currentInvoice.job_id}`, {
            headers: { Authorization: `Bearer ${accessToken}` }
          });
          if (!jobRes.ok) throw new Error("Failed to load job details.");
          const jobData = await jobRes.json();
          jobCustomer = jobData.customer;
          setCustomer(jobCustomer);

          // Bypass signature since customer already opened payment link
          setStep("payment_select");
        } else {
          // Standard tech checkout flow - fetch job first
          const jobRes = await fetch(`${API_URL}/jobs/${id}`, {
            headers: { Authorization: `Bearer ${accessToken}` }
          });
          if (!jobRes.ok) throw new Error("Failed to load job details.");
          const jobData = await jobRes.json();
          setCustomer(jobData.customer);

          // Get or create draft invoice
          const invRes = await fetch(`${API_URL}/invoices/jobs/${id}/invoice/draft`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${accessToken}`,
              "Content-Type": "application/json"
            },
            body: JSON.stringify({ redeem_points: 0 })
          });
          if (!invRes.ok) throw new Error("Failed to load or draft invoice.");
          currentInvoice = await invRes.json();
          setInvoice(currentInvoice);

          // If signature already exists, go directly to payment select
          // We can check if status is already paid
          if (currentInvoice.status === "paid") {
            setStep("success");
          } else {
            setStep("signature");
          }
        }
      } catch (err: any) {
        console.error(err);
        setError(err.message || "Failed to initialize payment details.");
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [id, accessToken, isMockPaymentLink, targetInvoiceId]);

  // Setup Canvas Drawing
  useEffect(() => {
    if (step !== "signature" || !canvasRef.current) return;
    const canvas = canvasRef.current;
    
    // Support High DPI displays
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.scale(dpr, dpr);
      ctx.strokeStyle = "#a5b4fc"; // Indigo 300
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
    }
  }, [step]);

  // Polling loop for Payment Link status
  useEffect(() => {
    if (step !== "polling" || !invoice || !accessToken) return;

    let isMounted = true;
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/invoices/${invoice.id}`, {
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!res.ok) return;
        const updated = await res.json();
        if (updated.status === "paid" && isMounted) {
          setInvoice(updated);
          setStep("success");
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error("Error polling invoice status:", err);
      }
    }, 3000);

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [step, invoice, accessToken]);

  // Confetti Animation Effect
  useEffect(() => {
    if (step !== "success" || !confettiCanvasRef.current) return;
    const canvas = confettiCanvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    interface Particle {
      x: number;
      y: number;
      size: number;
      color: string;
      speedX: number;
      speedY: number;
      rotation: number;
      rotationSpeed: number;
    }

    const colors = ["#818cf8", "#6366f1", "#4f46e5", "#34d399", "#059669", "#fb7185", "#f43f5e"];
    const particles: Particle[] = Array.from({ length: 120 }).map(() => ({
      x: Math.random() * canvas.width,
      y: Math.random() * -canvas.height - 20,
      size: Math.random() * 8 + 4,
      color: colors[Math.floor(Math.random() * colors.length)],
      speedX: Math.random() * 4 - 2,
      speedY: Math.random() * 5 + 3,
      rotation: Math.random() * 360,
      rotationSpeed: Math.random() * 4 - 2
    }));

    let animationId: number;
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      let alive = false;

      particles.forEach((p) => {
        p.y += p.speedY;
        p.x += p.speedX;
        p.rotation += p.rotationSpeed;

        if (p.y < canvas.height) {
          alive = true;
        }

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        ctx.restore();
      });

      if (alive) {
        animationId = requestAnimationFrame(animate);
      }
    };

    animate();

    const handleResize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", handleResize);
    };
  }, [step]);

  // Drawing Handlers
  const startDrawing = (x: number, y: number) => {
    isDrawingRef.current = true;
    lastXRef.current = x;
    lastYRef.current = y;
    hasDrawnRef.current = true;
  };

  const draw = (x: number, y: number) => {
    if (!isDrawingRef.current || !canvasRef.current) return;
    const ctx = canvasRef.current.getContext("2d");
    if (!ctx) return;

    ctx.beginPath();
    ctx.moveTo(lastXRef.current, lastYRef.current);
    ctx.lineTo(x, y);
    ctx.stroke();

    lastXRef.current = x;
    lastYRef.current = y;
  };

  const stopDrawing = () => {
    isDrawingRef.current = false;
  };

  // Event Handlers for Canvas (Mouse)
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    startDrawing(e.clientX - rect.left, e.clientY - rect.top);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    draw(e.clientX - rect.left, e.clientY - rect.top);
  };

  // Event Handlers for Canvas (Touch)
  const handleTouchStart = (e: React.TouchEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || e.touches.length === 0) return;
    const touch = e.touches[0];
    startDrawing(touch.clientX - rect.left, touch.clientY - rect.top);
  };

  const handleTouchMove = (e: React.TouchEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || e.touches.length === 0) return;
    const touch = e.touches[0];
    draw(touch.clientX - rect.left, touch.clientY - rect.top);
  };

  const clearSignature = () => {
    if (!canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      hasDrawnRef.current = false;
    }
  };

  // Upload signature
  const saveSignature = async () => {
    if (!invoice || !hasDrawnRef.current || !canvasRef.current) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const base64Image = canvasRef.current.toDataURL("image/png");
      const res = await fetch(`${API_URL}/invoices/${invoice.id}/signature`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ signature_base64: base64Image })
      });

      if (!res.ok) throw new Error("Failed to save signature.");
      const updated = await res.json();
      setInvoice(updated);
      setStep("payment_select");
    } catch (err: any) {
      setError(err.message || "Failed to upload signature. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Payment Selection/Submission
  const handlePaymentInitiate = async () => {
    if (!invoice) return;
    setIsSubmitting(true);
    setError(null);

    try {
      if (selectedMethod === "card_present") {
        // Create Payment Intent
        const res = await fetch(`${API_URL}/invoices/${invoice.id}/pay/intent`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!res.ok) throw new Error("Failed to initialize Stripe Payment.");
        const intentData = await res.json();

        setMockClientSecret(intentData.client_secret);
        setMockPaymentIntentId(intentData.payment_intent_id);
        setStep("card_present_simulate");
      } else if (selectedMethod === "link") {
        // Create Payment Link
        const res = await fetch(`${API_URL}/invoices/${invoice.id}/pay/link`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (!res.ok) throw new Error("Failed to generate payment link.");
        const linkData = await res.json();
        
        setPaymentLinkUrl(linkData.url);
        setStep("polling");
      } else {
        // Manual Cash/Check payment
        const res = await fetch(`${API_URL}/invoices/${invoice.id}/pay/manual`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${accessToken}`,
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            payment_method: selectedMethod,
            notes: manualNotes || undefined
          })
        });
        if (!res.ok) throw new Error("Failed to record manual payment.");
        const updated = await res.json();
        setInvoice(updated);
        setStep("success");
      }
    } catch (err: any) {
      setError(err.message || "An error occurred while initiating payment.");
    } finally {
      setIsSubmitting(false);
    }
  };

  // Simulate Payment Success (Webhook call for Card Reader or Customer Link mockup)
  const triggerMockPaymentWebhook = async (intentId: string) => {
    setIsSubmitting(true);
    setError(null);

    try {
      const webhookPayload = {
        type: "payment_intent.succeeded",
        data: {
          object: {
            id: intentId,
            amount: invoice?.total_cents,
            latest_charge: `ch_mock_${Math.random().toString(36).substr(2, 9)}`,
            metadata: {
              invoice_id: invoice?.id,
              company_id: invoice?.company_id
            }
          }
        }
      };

      const res = await fetch(`${API_URL}/webhooks/stripe`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(webhookPayload)
      });

      if (!res.ok) throw new Error("Mock webhook submission failed.");

      // Fetch the updated invoice state to verify payment reflected
      if (invoice) {
        const invRes = await fetch(`${API_URL}/invoices/${invoice.id}`, {
          headers: { Authorization: `Bearer ${accessToken}` }
        });
        if (invRes.ok) {
          const updated = await invRes.ok ? await invRes.json() : null;
          if (updated && updated.status === "paid") {
            setInvoice(updated);
            setStep("success");
            return;
          }
        }
      }
      
      // Fallback
      setStep("success");
    } catch (err: any) {
      setError(err.message || "Failed to simulate payment completion.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#070a13] text-slate-100 flex flex-col items-center justify-center p-6">
        <Loader2 className="w-10 h-10 text-indigo-400 animate-spin mb-4" />
        <p className="text-slate-400 text-xs font-bold uppercase tracking-wider">Loading Invoice Details...</p>
      </div>
    );
  }

  if (!invoice || !customer) {
    return (
      <div className="min-h-screen bg-[#070a13] text-slate-100 flex flex-col items-center justify-center p-6">
        <AlertCircle className="w-12 h-12 text-rose-500 mb-4" />
        <p className="text-rose-400 text-sm font-black mb-2">Error Loading Context</p>
        <p className="text-slate-400 text-xs mb-6 text-center">Invoice or Customer records could not be resolved.</p>
        <button
          onClick={() => router.back()}
          className="bg-slate-900 border border-slate-800 hover:bg-slate-850 text-indigo-400 font-bold px-6 py-2.5 rounded-xl cursor-pointer"
        >
          Go Back
        </button>
      </div>
    );
  }

  const invoiceAmountDollars = invoice.total_cents / 100;

  return (
    <div className="min-h-screen bg-[#070a13] text-slate-100 flex flex-col items-center relative overflow-hidden font-sans">
      {/* Background radial glow */}
      <div className="absolute top-[-20%] left-[-20%] w-[80%] h-[80%] rounded-full bg-indigo-500/10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-20%] w-[80%] h-[80%] rounded-full bg-emerald-500/5 blur-[120px] pointer-events-none" />

      {step === "success" && (
        <canvas ref={confettiCanvasRef} className="absolute inset-0 pointer-events-none z-50 w-full h-full" />
      )}

      {/* Header */}
      <header className="w-full max-w-lg px-6 pt-6 flex justify-between items-center z-10 shrink-0">
        <button
          onClick={() => {
            if (isMockPaymentLink) {
              // Mock link doesn't go back in routing
              return;
            }
            if (step === "payment_select") {
              setStep("signature");
            } else if (step === "polling" || step === "card_present_simulate") {
              setStep("payment_select");
            } else {
              router.back();
            }
          }}
          disabled={step === "success" || isMockPaymentLink}
          className="bg-slate-900/60 border border-slate-800/80 hover:bg-slate-850 text-slate-400 hover:text-white p-2.5 rounded-xl cursor-pointer disabled:opacity-30 disabled:pointer-events-none transition"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="text-right">
          <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block">Checkout Engine</span>
          <span className="text-xs font-extrabold text-indigo-300">Invoice {invoice.invoice_number}</span>
        </div>
      </header>

      <main className="w-full max-w-lg px-6 py-6 flex-1 flex flex-col gap-6 z-10 overflow-y-auto">
        {/* Error Alert */}
        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 p-4 rounded-2xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
            <div className="flex-1 flex flex-col gap-1">
              <span className="text-xs font-extrabold text-rose-400">Transaction Failed</span>
              <p className="text-[11px] text-slate-300 leading-relaxed">{error}</p>
            </div>
          </div>
        )}

        {/* CUSTOMER CHECKOUT VIEW (MOCK PAYMENT LINK REDIRECTED) */}
        {isMockPaymentLink && step === "payment_select" ? (
          <div className="flex flex-col gap-5 flex-1 justify-center py-4">
            <div className="bg-slate-900/40 border border-indigo-500/30 backdrop-blur-md rounded-3xl p-6 flex flex-col gap-5 shadow-2xl relative">
              <div className="absolute top-0 right-0 bg-indigo-500 text-white text-[9px] font-black uppercase tracking-wider px-3 py-1 rounded-bl-2xl rounded-tr-[22px]">
                Stripe Connect Sandbox
              </div>

              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-300">
                  <CreditCard className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-sm font-black text-white">Stripe Payment Portal</h2>
                  <p className="text-[10px] text-slate-400">Mocking secure transaction for {customer.first_name} {customer.last_name}</p>
                </div>
              </div>

              <div className="border-t border-b border-slate-850 py-4 flex flex-col gap-2">
                <div className="flex justify-between items-center text-[11px] text-slate-400">
                  <span>Invoice Number:</span>
                  <span className="font-bold text-white">{invoice.invoice_number}</span>
                </div>
                <div className="flex justify-between items-center text-[11px] text-slate-400">
                  <span>Billed To:</span>
                  <span className="font-bold text-white">{customer.first_name} {customer.last_name}</span>
                </div>
                <div className="flex justify-between items-center text-xs mt-2 pt-2 border-t border-slate-850/50">
                  <span className="font-extrabold text-white">Total Charge:</span>
                  <span className="text-lg font-black text-emerald-400">${invoiceAmountDollars.toFixed(2)}</span>
                </div>
              </div>

              <div className="flex flex-col gap-3 text-slate-400 text-[11px] leading-relaxed bg-slate-950/50 border border-slate-850 p-4 rounded-2xl">
                <div className="flex gap-2">
                  <Info className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                  <p>This screen simulates the customer-facing Stripe checkout screen that would normally load via the secure Payment Link.</p>
                </div>
              </div>

              <button
                onClick={() => triggerMockPaymentWebhook(invoice.id)}
                disabled={isSubmitting}
                className="w-full py-4 rounded-2xl font-black text-xs text-white border-none shadow-xl cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-450 hover:to-teal-550 transition duration-200 flex items-center justify-center gap-2 shadow-emerald-500/10 disabled:opacity-50"
              >
                {isSubmitting ? <Loader2 className="w-4.5 h-4.5 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                <span>Authorize & Pay Invoice (${invoiceAmountDollars.toFixed(2)})</span>
              </button>
            </div>
          </div>
        ) : (
          /* REGULAR TECHNICIAN WORKFLOW */
          <>
            {/* Step 1: Signature Pad */}
            {step === "signature" && (
              <div className="flex flex-col gap-5 flex-1">
                {/* Invoice Summary Card */}
                <div className="bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-3xl p-5 flex flex-col gap-4 shadow-xl">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Invoice Balance Due</span>
                  <div className="flex justify-between items-baseline">
                    <span className="text-3xl font-black text-emerald-400">${invoiceAmountDollars.toFixed(2)}</span>
                    <span className="text-[11px] font-extrabold text-slate-400">Total includes parts, labor, & tax</span>
                  </div>
                  <div className="border-t border-slate-850 pt-3 mt-1 flex justify-between items-center text-[10px] text-slate-400">
                    <span>Customer: <strong className="text-white">{customer.first_name} {customer.last_name}</strong></span>
                    <span>Phone: <strong className="text-white">{customer.phone || "N/A"}</strong></span>
                  </div>
                </div>

                {/* Signature Board */}
                <div className="bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-3xl p-5 flex-1 flex flex-col gap-4 shadow-xl min-h-[300px]">
                  <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                      <label className="text-[11px] text-slate-300 font-black uppercase tracking-wider block">
                        Customer Signature Required
                      </label>
                    </div>
                    <button
                      onClick={clearSignature}
                      className="bg-transparent border-none text-[10px] text-indigo-400 hover:text-indigo-300 font-bold uppercase cursor-pointer"
                    >
                      Clear Pad
                    </button>
                  </div>

                  <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-950/60 overflow-hidden relative min-h-[200px] flex items-center justify-center">
                    <canvas
                      ref={canvasRef}
                      onMouseDown={handleMouseDown}
                      onMouseMove={handleMouseMove}
                      onMouseUp={stopDrawing}
                      onMouseLeave={stopDrawing}
                      onTouchStart={handleTouchStart}
                      onTouchMove={handleTouchMove}
                      onTouchEnd={stopDrawing}
                      className="w-full h-full absolute inset-0 cursor-crosshair touch-none"
                    />
                    <div className="pointer-events-none text-slate-600 font-extrabold text-[10px] uppercase tracking-widest border-b border-dashed border-slate-800 w-[80%] text-center pb-2 mt-20">
                      Sign Here
                    </div>
                  </div>

                  <p className="text-[10px] text-slate-500 text-center leading-relaxed">
                    By signing, the customer approves the completed work orders and accepts invoice line items.
                  </p>

                  <button
                    onClick={saveSignature}
                    disabled={isSubmitting}
                    className="w-full py-4 rounded-2xl font-black text-xs text-white border-none shadow-xl cursor-pointer bg-gradient-to-r from-indigo-500 to-purple-650 hover:from-indigo-455 hover:to-purple-600 transition duration-200 flex items-center justify-center gap-2 shadow-indigo-500/10 disabled:opacity-50"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Uploading Signature...</span>
                      </>
                    ) : (
                      <span>Accept Signature & Proceed</span>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Payment Method Select */}
            {step === "payment_select" && (
              <div className="flex flex-col gap-5 flex-1">
                {/* Amount Display */}
                <div className="bg-slate-900/40 border border-slate-850 p-6 rounded-3xl text-center shadow-xl backdrop-blur-md">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider block mb-1">Total Charge</span>
                  <span className="text-3xl font-black text-emerald-400">${invoiceAmountDollars.toFixed(2)}</span>
                  <div className="mt-4 pt-3 border-t border-slate-850 flex justify-center gap-4 text-[10px] text-slate-400 font-bold">
                    <span className="flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-indigo-400" /> Signed & Approved</span>
                  </div>
                </div>

                <div className="bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-3xl p-5 flex flex-col gap-4 shadow-xl">
                  <label className="text-[11px] text-slate-300 font-black uppercase tracking-wider block">
                    Choose Collection Method
                  </label>

                  <div className="grid grid-cols-1 gap-2.5">
                    {[
                      {
                        id: "card_present",
                        label: "Card Present (Tap / Reader)",
                        desc: "Stripe Connect EMV Card Reader transaction",
                        icon: <CreditCard className="w-5 h-5 text-indigo-400" />
                      },
                      {
                        id: "link",
                        label: "Send Secure Payment Link",
                        desc: "Dispatches SMS/Email with credit card link",
                        icon: <Send className="w-5 h-5 text-emerald-450" />
                      },
                      {
                        id: "cash",
                        label: "Cash Collection",
                        desc: "Collect and log standard cash currency",
                        icon: <DollarSign className="w-5 h-5 text-teal-400" />
                      },
                      {
                        id: "check",
                        label: "Check Payment",
                        desc: "Log physical check reference number",
                        icon: <Receipt className="w-5 h-5 text-purple-400" />
                      }
                    ].map((method) => (
                      <button
                        key={method.id}
                        onClick={() => setSelectedMethod(method.id as any)}
                        className={`flex items-center gap-4 p-4 rounded-2xl border text-left cursor-pointer transition ${
                          selectedMethod === method.id
                            ? "bg-slate-850/80 border-indigo-500 text-white shadow-lg shadow-indigo-500/5"
                            : "bg-slate-950/20 border-slate-850 text-slate-400 hover:text-slate-200 hover:border-slate-800"
                        }`}
                      >
                        <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 shrink-0">
                          {method.icon}
                        </div>
                        <div className="flex-1">
                          <span className="text-xs font-extrabold block text-slate-100">{method.label}</span>
                          <span className="text-[10px] text-slate-500 font-semibold mt-0.5 block">{method.desc}</span>
                        </div>
                      </button>
                    ))}
                  </div>

                  {/* Cash/Check Notes Field */}
                  {(selectedMethod === "cash" || selectedMethod === "check") && (
                    <div className="flex flex-col gap-2 mt-2 animate-fadeIn">
                      <label className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">
                        Manual Logging Notes (Optional)
                      </label>
                      <input
                        type="text"
                        value={manualNotes}
                        onChange={(e) => setManualNotes(e.target.value)}
                        placeholder={selectedMethod === "check" ? "e.g., Check #1024" : "e.g., Paid with $100 bill"}
                        className="w-full bg-slate-950/80 border border-slate-800 rounded-xl py-3 px-4 text-slate-200 text-xs font-semibold placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
                      />
                    </div>
                  )}

                  <button
                    onClick={handlePaymentInitiate}
                    disabled={isSubmitting}
                    className="w-full py-4 rounded-2xl font-black text-xs text-white border-none shadow-xl cursor-pointer bg-gradient-to-r from-emerald-500 to-teal-650 hover:from-emerald-450 hover:to-teal-600 transition duration-200 flex items-center justify-center gap-2 mt-4 shadow-emerald-500/10"
                  >
                    {isSubmitting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Processing request...</span>
                      </>
                    ) : (
                      <span>Collect Payment (${invoiceAmountDollars.toFixed(2)})</span>
                    )}
                  </button>
                </div>
              </div>
            )}

            {/* Polling State (Waiting for Payment Link) */}
            {step === "polling" && (
              <div className="flex flex-col gap-5 flex-1 justify-center py-6">
                <div className="bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-3xl p-6 text-center shadow-xl flex flex-col items-center gap-5">
                  <div className="relative w-14 h-14 flex items-center justify-center">
                    <Loader2 className="w-14 h-14 text-indigo-500 animate-spin absolute" />
                    <Send className="w-5 h-5 text-indigo-400 animate-pulse" />
                  </div>
                  <div>
                    <h3 className="text-sm font-black text-white">Payment Link Sent</h3>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      A payment link was dispatched to {customer.phone || customer.email || "customer"}.
                    </p>
                  </div>

                  <div className="bg-slate-950/50 border border-slate-850 p-4 rounded-2xl text-left w-full flex flex-col gap-2">
                    <span className="text-[9px] text-slate-500 font-bold uppercase tracking-wider block">Real-time status</span>
                    <span className="text-xs font-semibold text-slate-300 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                      Waiting for customer payment...
                    </span>
                  </div>

                  {paymentLinkUrl && paymentLinkUrl.includes("mock_payment_link=true") && (
                    <div className="border-t border-slate-850 pt-4 mt-2 w-full flex flex-col gap-2">
                      <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Dev Sandbox Test Link</span>
                      <a
                        href={paymentLinkUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 hover:text-indigo-350 p-3 rounded-xl font-bold text-xs inline-block break-all hover:bg-indigo-550/5 transition cursor-pointer"
                      >
                        Open Mock Customer Portal &rarr;
                      </a>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Card Present Simulation Screen */}
            {step === "card_present_simulate" && (
              <div className="flex flex-col gap-5 flex-1 justify-center py-6">
                <div className="bg-slate-900/40 border border-slate-800/80 backdrop-blur-md rounded-3xl p-6 text-center shadow-xl flex flex-col items-center gap-6">
                  <div className="w-16 h-16 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-inner">
                    <CreditCard className="w-8 h-8 animate-pulse" />
                  </div>
                  <div>
                    <h3 className="text-sm font-black text-white">Stripe Reader Connection</h3>
                    <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                      Terminal intent created. In production, this handshakes with the mobile Bluetooth or Wi-Fi reader.
                    </p>
                  </div>

                  <div className="bg-indigo-500/10 border border-indigo-500/20 p-4 rounded-2xl text-[11px] text-left w-full text-indigo-300 leading-relaxed">
                    <strong>Payment Intent Token:</strong>
                    <code className="block mt-1 font-mono text-[9px] text-slate-400 break-all select-all bg-slate-950 p-2.5 rounded-lg border border-slate-900">
                      {mockClientSecret}
                    </code>
                  </div>

                  <div className="flex flex-col gap-2.5 w-full">
                    <button
                      onClick={() => mockPaymentIntentId && triggerMockPaymentWebhook(mockPaymentIntentId)}
                      disabled={isSubmitting}
                      className="w-full py-4 rounded-2xl font-black text-xs text-white border-none shadow-xl cursor-pointer bg-gradient-to-r from-emerald-500 to-indigo-600 hover:from-emerald-450 hover:to-indigo-500 transition duration-200 flex items-center justify-center gap-2"
                    >
                      {isSubmitting ? <Loader2 className="w-4.5 h-4.5 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                      <span>Simulate Card Tap / Chip Insert</span>
                    </button>
                    <button
                      onClick={() => setStep("payment_select")}
                      className="w-full py-3 rounded-2xl font-extrabold text-[11px] text-slate-400 hover:text-white bg-slate-950/40 hover:bg-slate-950/80 border border-slate-850 cursor-pointer transition"
                    >
                      Cancel Transaction
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}

        {/* Success Screen */}
        {step === "success" && (
          <div className="flex flex-col gap-6 flex-1 justify-center py-4 animate-scaleUp">
            <div className="bg-slate-900/40 border border-emerald-500/20 backdrop-blur-md rounded-3xl p-6 text-center shadow-2xl flex flex-col items-center gap-5 relative">
              <div className="w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-500/5">
                <CheckCircle2 className="w-9 h-9 animate-bounce" />
              </div>
              <div>
                <h3 className="text-lg font-black text-white">Payment Received!</h3>
                <p className="text-xs text-slate-400 mt-1 font-semibold">
                  Invoice {invoice.invoice_number} is fully paid and settled.
                </p>
              </div>

              {/* Receipt Summary */}
              <div className="bg-slate-950/60 border border-slate-850 rounded-2xl p-4 w-full flex flex-col gap-2.5 text-xs text-left">
                <div className="flex justify-between items-center text-slate-500 font-bold uppercase tracking-wider text-[9px]">
                  <span>Receipt Details</span>
                  <span className="text-emerald-400 text-[10px] font-black">Settled</span>
                </div>
                <div className="border-t border-slate-850/50 my-1" />
                <div className="flex justify-between items-center">
                  <span className="text-slate-400 font-medium">Billed Amount:</span>
                  <span className="font-extrabold text-slate-200">${(invoice.subtotal_cents / 100).toFixed(2)}</span>
                </div>
                {invoice.discount_cents > 0 && (
                  <div className="flex justify-between items-center text-rose-450">
                    <span>Discounts/Redemptions:</span>
                    <span className="font-extrabold">-${(invoice.discount_cents / 100).toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between items-center">
                  <span className="text-slate-400 font-medium">Tax Calculated:</span>
                  <span className="font-extrabold text-slate-200">${(invoice.tax_cents / 100).toFixed(2)}</span>
                </div>
                <div className="border-t border-slate-850/50 my-1" />
                <div className="flex justify-between items-center font-black">
                  <span className="text-white">Amount Collected:</span>
                  <span className="text-emerald-400 text-sm">${invoiceAmountDollars.toFixed(2)}</span>
                </div>
              </div>

              <div className="bg-emerald-500/5 border border-emerald-500/10 p-4 rounded-2xl text-[11px] text-slate-400 leading-relaxed w-full text-center">
                Loyalty points credited and QuickBooks sync queued successfully.
              </div>

              <button
                onClick={() => {
                  if (isMockPaymentLink) {
                    // Close tab or redirect somewhere neutral
                    alert("Mock payment link testing complete! You can close this tab.");
                  } else {
                    router.push(`/app/jobs/${id}`);
                  }
                }}
                className="w-full py-4 rounded-2xl font-black text-xs text-white border-none shadow-xl cursor-pointer bg-gradient-to-r from-emerald-500 to-indigo-650 hover:from-emerald-450 hover:to-indigo-600 transition duration-200"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
