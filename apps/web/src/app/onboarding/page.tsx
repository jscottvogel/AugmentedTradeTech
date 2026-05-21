"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../hooks/useAuth";

interface StepConfig {
  number: number;
  title: string;
  estTime: string;
  description: string;
}

const STEPS: StepConfig[] = [
  { number: 1, title: "Account", estTime: "2 min", description: "Create your company profile and owner login" },
  { number: 2, title: "Profile", estTime: "3 min", description: "Configure your trades, service area, and hours" },
  { number: 3, title: "Plan", estTime: "1 min", description: "Select a subscription plan that fits your business" },
  { number: 4, title: "Stripe", estTime: "2 min", description: "Connect Stripe to accept payments on the field" },
  { number: 5, title: "QuickBooks", estTime: "2 min", description: "Sync invoices, payments, and customers with QBO" },
  { number: 6, title: "Invite Tech", estTime: "1 min", description: "Invite your first service technician" },
  { number: 7, title: "Website Widget", estTime: "1 min", description: "Get the booking widget for your website" },
  { number: 8, title: "Complete", estTime: "1 min", description: "All set! Access your field operations dashboard" },
];

export default function OnboardingPage() {
  const { user, accessToken, loginWithPassword } = useAuth();
  const router = useRouter();

  // Wizard state
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [maxAllowedStep, setMaxAllowedStep] = useState<number>(1);
  const [isLoadingState, setIsLoadingState] = useState<boolean>(true);
  const [apiError, setApiError] = useState<string | null>(null);

  // Form Fields
  // Step 1: Account Signup
  const [companyName, setCompanyName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Step 2: Profile
  const [selectedTrades, setSelectedTrades] = useState<string[]>([]);
  const [serviceAreaZips, setServiceAreaZips] = useState("");
  const [businessHoursStart, setBusinessHoursStart] = useState("08:00");
  const [businessHoursEnd, setBusinessHoursEnd] = useState("17:00");
  const [logoUrl, setLogoUrl] = useState("");

  // Step 3: Plan
  const [selectedPlan, setSelectedPlan] = useState("");

  // Step 4: Stripe
  const [stripeConnected, setStripeConnected] = useState(false);

  // Step 5: QuickBooks
  const [qboConnected, setQboConnected] = useState(false);

  // Step 6: Invite Tech
  const [techEmail, setTechEmail] = useState("");
  const [techPhone, setTechPhone] = useState("");

  // Step 7: Widget copied status
  const [widgetCopied, setWidgetCopied] = useState(false);

  // Dynamic CSS injection for beautiful backgrounds, keyframes, and glows
  useEffect(() => {
    const style = document.createElement("style");
    style.innerHTML = `
      @keyframes float {
        0%, 100% { transform: translateY(0px) rotate(0deg); }
        50% { transform: translateY(-10px) rotate(1deg); }
      }
      @keyframes pulseGlow {
        0%, 100% { opacity: 0.15; }
        50% { opacity: 0.3; }
      }
      .glowing-bg {
        position: absolute;
        width: 600px;
        height: 600px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(147, 51, 234, 0.2) 0%, rgba(0,0,0,0) 70%);
        filter: blur(80px);
        z-index: 0;
        pointer-events: none;
        animation: float 20s ease-in-out infinite;
      }
      .glass-container {
        background: rgba(18, 18, 24, 0.65);
        backdrop-filter: blur(25px);
        -webkit-backdrop-filter: blur(25px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.3);
      }
      .glass-card {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);
      }
      .glass-card:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(147, 51, 234, 0.35);
        transform: translateY(-2px);
        box-shadow: 0 10px 25px rgba(147, 51, 234, 0.1);
      }
      .glass-input {
        background: rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.08);
        color: #fff;
        transition: all 0.2s ease;
      }
      .glass-input:focus {
        border-color: #9333ea;
        box-shadow: 0 0 12px rgba(147, 51, 234, 0.3);
        outline: none;
      }
      /* Custom Scrollbar */
      ::-webkit-scrollbar {
        width: 8px;
      }
      ::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.02);
      }
      ::-webkit-scrollbar-thumb {
        background: rgba(147, 51, 234, 0.3);
        border-radius: 4px;
      }
      ::-webkit-scrollbar-thumb:hover {
        background: rgba(147, 51, 234, 0.5);
      }
    `;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  // Fetch company onboarding state on mount/login
  useEffect(() => {
    async function fetchState() {
      if (!accessToken || !user || !user.company_id) {
        setIsLoadingState(false);
        return;
      }

      try {
        const res = await fetch(`http://localhost:8000/onboarding/${user.company_id}`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        });

        if (res.ok) {
          const data = await res.json();
          // Load model details to state
          setCompanyName(data.name || "");
          setSelectedTrades(data.trades || []);
          if (data.service_area_zips) {
            setServiceAreaZips(data.service_area_zips.join(", "));
          }
          if (data.business_hours) {
            setBusinessHoursStart(data.business_hours.start || "08:00");
            setBusinessHoursEnd(data.business_hours.end || "17:00");
          }
          setLogoUrl(data.logo_url || "");
          setStripeConnected(!!data.stripe_account_id);
          setQboConnected(!!data.qbo_realm_id);

          const backendStep = data.onboarding_step || 1;
          setMaxAllowedStep(backendStep);
          setCurrentStep(backendStep);
        }
      } catch (err) {
        console.error("Failed to load onboarding state", err);
      } finally {
        setIsLoadingState(false);
      }
    }

    fetchState();
  }, [accessToken, user]);

  // Handle Step Submissions
  // Step 1: Account
  const handleAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);

    if (!companyName || !ownerName || !email || !password) {
      setApiError("All fields are required");
      return;
    }

    try {
      const res = await fetch("http://localhost:8000/onboarding/company", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: companyName,
          owner_name: ownerName,
          email,
          password,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Account creation failed");
      }

      const data = await res.json();
      // Use standard credentials login flow to trigger AuthProvider updating context
      await loginWithPassword(email, password);

      setMaxAllowedStep(2);
      setCurrentStep(2);
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 2: Profile
  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);

    if (selectedTrades.length === 0) {
      setApiError("Please select at least one trade");
      return;
    }

    const zips = serviceAreaZips
      .split(/[\s,]+/)
      .map((z) => z.trim())
      .filter((z) => z.length > 0);

    if (zips.length === 0) {
      setApiError("Please enter at least one service zip code");
      return;
    }

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          trades: selectedTrades,
          service_area_zips: zips,
          business_hours: {
            start: businessHoursStart,
            end: businessHoursEnd,
          },
          logo_url: logoUrl || null,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to update business profile");
      }

      const data = await res.json();
      setMaxAllowedStep(3);
      setCurrentStep(3);
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 3: Plan Selection
  const handlePlanSubmit = async (plan: string) => {
    setApiError(null);
    setSelectedPlan(plan);

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/plan`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ plan }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to save plan selection");
      }

      const data = await res.json();
      setMaxAllowedStep(4);
      setCurrentStep(4);
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 4: Stripe Connect Mock redirect
  const handleStripeConnect = async () => {
    setApiError(null);

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/stripe`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to initiate Stripe");
      }

      const data = await res.json();
      // Redirect to the mock callback trigger
      window.location.href = data.url;
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 5: QuickBooks Connect (Connect or Skip)
  const handleQboConnect = async (connect: boolean) => {
    setApiError(null);

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/quickbooks`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ connect }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to configure QuickBooks");
      }

      const data = await res.json();
      setQboConnected(connect);
      setMaxAllowedStep(6);
      setCurrentStep(6);
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 6: Invite Technician
  const handleInviteTech = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/invite-tech`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          email: techEmail || null,
          phone: techPhone || null,
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to send technician invitation");
      }

      const data = await res.json();
      setMaxAllowedStep(7);
      setCurrentStep(7);
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Step 7: Website Widget Copy Code
  const copyWidgetCode = () => {
    const embedCode = `<!-- Augmented Trade Tech Booking Widget -->\n<div id="att-booking-widget" data-company-id="${user?.company_id}"></div>\n<script src="https://cdn.augmentedtradetech.com/widget.js" async></script>`;
    navigator.clipboard.writeText(embedCode);
    setWidgetCopied(true);
    setTimeout(() => setWidgetCopied(false), 3000);
  };

  const handleWidgetNext = () => {
    setMaxAllowedStep(8);
    setCurrentStep(8);
  };

  // Step 8: Complete Onboarding
  const handleFinishOnboarding = async () => {
    setApiError(null);

    try {
      const res = await fetch(`http://localhost:8000/onboarding/${user?.company_id}/complete`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to complete onboarding");
      }

      router.push("/");
    } catch (err: any) {
      setApiError(err.message || "An error occurred");
    }
  };

  // Helper: toggle trade array
  const toggleTrade = (trade: string) => {
    if (selectedTrades.includes(trade)) {
      setSelectedTrades(selectedTrades.filter((t) => t !== trade));
    } else {
      setSelectedTrades([...selectedTrades, trade]);
    }
  };

  // Click handler for Sidebar Step Navigation (resumable navigation)
  const handleStepClick = (stepNum: number) => {
    if (stepNum <= maxAllowedStep) {
      setCurrentStep(stepNum);
    }
  };

  // Calculate estimated time remaining
  const calculateTimeRemaining = (): string => {
    const remainingSteps = STEPS.slice(currentStep - 1);
    let totalMinutes = 0;
    remainingSteps.forEach((s) => {
      const mins = parseInt(s.estTime.split(" ")[0]) || 0;
      totalMinutes += mins;
    });
    return `${totalMinutes} min`;
  };

  if (isLoadingState && accessToken) {
    return (
      <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex items-center justify-center font-sans">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 border-4 border-purple-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="mt-4 text-zinc-400 font-medium">Resuming your onboarding session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] flex flex-col items-center justify-center font-sans p-6 relative overflow-hidden">
      {/* Decorative Blur Background Components */}
      <div className="glowing-bg top-[-10%] left-[-10%]" style={{ animationDelay: "0s" }}></div>
      <div className="glowing-bg bottom-[-10%] right-[-10%]" style={{ animationDelay: "-5s", background: "radial-gradient(circle, rgba(147, 51, 234, 0.15) 0%, rgba(0,0,0,0) 70%)" }}></div>

      <div className="w-full max-w-5xl glass-container rounded-2xl flex flex-col md:flex-row overflow-hidden relative z-10 min-h-[620px]">
        
        {/* Step Progress Sidebar */}
        <div className="w-full md:w-80 bg-black/40 border-b md:border-b-0 md:border-r border-white/5 p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-2 mb-6">
              <span className="text-xl font-bold bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent">
                Augmented Trade Tech
              </span>
            </div>
            
            <p className="text-xs text-zinc-400 uppercase tracking-widest font-semibold mb-4">Onboarding Steps</p>
            
            <div className="space-y-2">
              {STEPS.map((step) => {
                const isCompleted = step.number < maxAllowedStep;
                const isActive = step.number === currentStep;
                const isNavigable = step.number <= maxAllowedStep;

                return (
                  <button
                    key={step.number}
                    onClick={() => handleStepClick(step.number)}
                    disabled={!isNavigable}
                    className={`w-full text-left flex items-center justify-between p-3 rounded-lg border transition-all ${
                      isActive
                        ? "bg-purple-600/10 border-purple-500/30 text-white"
                        : isCompleted
                        ? "bg-zinc-950/20 border-white/5 text-zinc-300 hover:border-purple-600/20"
                        : "bg-transparent border-transparent text-zinc-600 cursor-not-allowed"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-sm transition-all ${
                          isCompleted
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : isActive
                            ? "bg-purple-600 text-white shadow-lg shadow-purple-600/30"
                            : "bg-zinc-900 border border-white/5 text-zinc-500"
                        }`}
                      >
                        {isCompleted ? (
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        ) : (
                          step.number
                        )}
                      </div>
                      <div className="flex flex-col">
                        <span className="font-semibold text-sm leading-tight">{step.title}</span>
                        <span className="text-[10px] text-zinc-400">Est: {step.estTime}</span>
                      </div>
                    </div>

                    {isCompleted && (
                      <span className="text-[10px] bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/20">
                        Done
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="mt-8 pt-4 border-t border-white/5 flex flex-col gap-1">
            <div className="flex items-center justify-between text-xs text-zinc-400">
              <span>Time Remaining:</span>
              <span className="font-bold text-white text-sm">{calculateTimeRemaining()}</span>
            </div>
            <div className="w-full bg-zinc-900 h-1.5 rounded-full overflow-hidden mt-2">
              <div
                className="bg-purple-600 h-full rounded-full transition-all duration-500 ease-out"
                style={{ width: `${(maxAllowedStep / STEPS.length) * 100}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* Wizard Main Content Pane */}
        <div className="flex-1 p-8 flex flex-col justify-between">
          <div className="max-w-xl w-full mx-auto">
            {/* Header info */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold tracking-tight">
                {STEPS[currentStep - 1].title} Setup
              </h2>
              <p className="text-zinc-400 mt-1 text-sm">
                {STEPS[currentStep - 1].description}
              </p>
            </div>

            {apiError && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg p-3 text-sm mb-6 flex items-center gap-2">
                <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{apiError}</span>
              </div>
            )}

            {/* Render Wizard Step Content */}
            
            {/* STEP 1: ACCOUNT */}
            {currentStep === 1 && (
              <form onSubmit={handleAccountSubmit} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Company Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Apex HVAC Services"
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Owner Full Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. John Doe"
                    value={ownerName}
                    onChange={(e) => setOwnerName(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Email Address</label>
                  <input
                    type="email"
                    required
                    placeholder="owner@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Password</label>
                  <input
                    type="password"
                    required
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                <button
                  type="submit"
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold p-3 rounded-lg text-sm transition-all mt-4"
                >
                  Create Account & Begin Onboarding
                </button>
              </form>
            )}

            {/* STEP 2: PROFILE */}
            {currentStep === 2 && (
              <form onSubmit={handleProfileSubmit} className="space-y-5">
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">Primary Trades</label>
                  <div className="grid grid-cols-2 gap-4">
                    <button
                      type="button"
                      onClick={() => toggleTrade("hvac")}
                      className={`p-4 rounded-xl border text-left flex flex-col justify-between h-28 glass-card ${
                        selectedTrades.includes("hvac")
                          ? "border-purple-600 bg-purple-600/10 text-white"
                          : "border-white/5 text-zinc-400"
                      }`}
                    >
                      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m11.314 11.314l.707.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
                      </svg>
                      <span className="font-semibold text-sm">HVAC Services</span>
                    </button>
                    
                    <button
                      type="button"
                      onClick={() => toggleTrade("garage_door")}
                      className={`p-4 rounded-xl border text-left flex flex-col justify-between h-28 glass-card ${
                        selectedTrades.includes("garage_door")
                          ? "border-purple-600 bg-purple-600/10 text-white"
                          : "border-white/5 text-zinc-400"
                      }`}
                    >
                      <svg className="w-8 h-8 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                      </svg>
                      <span className="font-semibold text-sm">Garage Door Repair</span>
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Service Area Zip Codes</label>
                  <input
                    type="text"
                    required
                    placeholder="Enter zip codes separated by commas (e.g. 75201, 75202, 75203)"
                    value={serviceAreaZips}
                    onChange={(e) => setServiceAreaZips(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Business Hours Start</label>
                    <input
                      type="time"
                      required
                      value={businessHoursStart}
                      onChange={(e) => setBusinessHoursStart(e.target.value)}
                      className="w-full glass-input p-3 rounded-lg text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Business Hours End</label>
                    <input
                      type="time"
                      required
                      value={businessHoursEnd}
                      onChange={(e) => setBusinessHoursEnd(e.target.value)}
                      className="w-full glass-input p-3 rounded-lg text-sm"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Company Logo URL (Optional)</label>
                  <input
                    type="url"
                    placeholder="https://example.com/logo.png"
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>

                <button
                  type="submit"
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold p-3 rounded-lg text-sm transition-all"
                >
                  Save Business Profile & Continue
                </button>
              </form>
            )}

            {/* STEP 3: PLAN */}
            {currentStep === 3 && (
              <div className="space-y-6">
                <div className="grid grid-cols-3 gap-4">
                  {/* Starter Card */}
                  <div className={`p-4 rounded-xl border flex flex-col justify-between h-[280px] glass-card ${selectedPlan === "starter" ? "border-purple-600 bg-purple-600/5" : "border-white/5"}`}>
                    <div>
                      <h3 className="font-bold text-md text-white">Starter</h3>
                      <p className="text-zinc-500 text-xs mt-1">Up to 3 technicians</p>
                      <div className="mt-4 flex items-baseline gap-1">
                        <span className="text-2xl font-extrabold">$49</span>
                        <span className="text-zinc-500 text-xs">/mo</span>
                      </div>
                      <ul className="text-[10px] text-zinc-400 mt-4 space-y-1">
                        <li>• Dispatch board</li>
                        <li>• Basic CRM</li>
                        <li>• Invoicing</li>
                      </ul>
                    </div>
                    <button
                      onClick={() => handlePlanSubmit("starter")}
                      className="w-full bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-3 rounded-lg text-xs transition-all"
                    >
                      Select Starter
                    </button>
                  </div>

                  {/* Professional Card */}
                  <div className={`p-4 rounded-xl border flex flex-col justify-between h-[280px] glass-card relative ${selectedPlan === "professional" ? "border-purple-600 bg-purple-600/5" : "border-white/5"}`}>
                    <div className="absolute top-0 right-4 transform -translate-y-1/2 bg-purple-600 text-white text-[8px] font-extrabold uppercase px-2 py-0.5 rounded-full border border-purple-500 shadow-lg">
                      Popular
                    </div>
                    <div>
                      <h3 className="font-bold text-md text-white">Professional</h3>
                      <p className="text-zinc-500 text-xs mt-1">Up to 10 technicians</p>
                      <div className="mt-4 flex items-baseline gap-1">
                        <span className="text-2xl font-extrabold">$129</span>
                        <span className="text-zinc-500 text-xs">/mo</span>
                      </div>
                      <ul className="text-[10px] text-zinc-400 mt-4 space-y-1">
                        <li>• Advanced scheduling</li>
                        <li>• Stripe integration</li>
                        <li>• QuickBooks sync</li>
                      </ul>
                    </div>
                    <button
                      onClick={() => handlePlanSubmit("professional")}
                      className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-2 px-3 rounded-lg text-xs transition-all"
                    >
                      Select Pro
                    </button>
                  </div>

                  {/* Enterprise Card */}
                  <div className={`p-4 rounded-xl border flex flex-col justify-between h-[280px] glass-card ${selectedPlan === "enterprise" ? "border-purple-600 bg-purple-600/5" : "border-white/5"}`}>
                    <div>
                      <h3 className="font-bold text-md text-white">Enterprise</h3>
                      <p className="text-zinc-500 text-xs mt-1">Unlimited technicians</p>
                      <div className="mt-4 flex items-baseline gap-1">
                        <span className="text-2xl font-extrabold">$299</span>
                        <span className="text-zinc-500 text-xs">/mo</span>
                      </div>
                      <ul className="text-[10px] text-zinc-400 mt-4 space-y-1">
                        <li>• Dedicated account support</li>
                        <li>• Custom integrations</li>
                        <li>• AI routes optimization</li>
                      </ul>
                    </div>
                    <button
                      onClick={() => handlePlanSubmit("enterprise")}
                      className="w-full bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-3 rounded-lg text-xs transition-all"
                    >
                      Select Enterprise
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 4: STRIPE */}
            {currentStep === 4 && (
              <div className="space-y-6 text-center py-6">
                <div className="w-16 h-16 bg-purple-600/10 border border-purple-500/20 text-purple-400 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-white">Accept Payments Digitally</h3>
                <p className="text-zinc-400 text-sm max-w-md mx-auto">
                  Accept credit card, Apple Pay, and Google Pay payments on the field using Stripe. Connect your existing Stripe account or set up a new merchant account in minutes.
                </p>

                {stripeConnected ? (
                  <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg p-4 inline-flex items-center gap-2 max-w-sm">
                    <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="font-semibold text-sm">Stripe Account Successfully Linked!</span>
                  </div>
                ) : (
                  <button
                    onClick={handleStripeConnect}
                    className="bg-[#635bff] hover:bg-[#5b54e7] text-white font-bold py-3 px-8 rounded-lg text-sm transition-all shadow-lg shadow-indigo-600/10"
                  >
                    Connect Stripe Account
                  </button>
                )}

                {stripeConnected && (
                  <div className="mt-8">
                    <button
                      onClick={() => setCurrentStep(5)}
                      className="bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 px-8 rounded-lg text-sm transition-all"
                    >
                      Continue
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* STEP 5: QUICKBOOKS */}
            {currentStep === 5 && (
              <div className="space-y-6 text-center py-6">
                <div className="w-16 h-16 bg-green-500/10 border border-green-500/20 text-green-400 rounded-full flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-white">Sync Invoices with QuickBooks</h3>
                <p className="text-zinc-400 text-sm max-w-md mx-auto">
                  Automatically sync jobs, service agreements, invoices, and payments directly into QuickBooks Online to save hours on bookkeeping.
                </p>

                <div className="flex flex-col sm:flex-row gap-4 justify-center items-center mt-6">
                  <button
                    onClick={() => handleQboConnect(true)}
                    className="bg-[#2ca01c] hover:bg-[#278d19] text-white font-bold py-3 px-6 rounded-lg text-sm transition-all w-full sm:w-auto"
                  >
                    Connect QuickBooks
                  </button>
                  <button
                    onClick={() => handleQboConnect(false)}
                    className="bg-transparent hover:bg-white/5 border border-white/10 text-zinc-400 font-bold py-3 px-6 rounded-lg text-sm transition-all w-full sm:w-auto"
                  >
                    Skip Integration for Now
                  </button>
                </div>
              </div>
            )}

            {/* STEP 6: INVITE TECH */}
            {currentStep === 6 && (
              <form onSubmit={handleInviteTech} className="space-y-4">
                <p className="text-zinc-400 text-sm mb-6 text-center">
                  Invite your first field service technician to download the technician app and view assigned service jobs.
                </p>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Technician Email Address</label>
                  <input
                    type="email"
                    placeholder="tech@company.com"
                    value={techEmail}
                    onChange={(e) => setTechEmail(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Technician Phone Number (Optional)</label>
                  <input
                    type="tel"
                    placeholder="e.g. +1 555-0199"
                    value={techPhone}
                    onChange={(e) => setTechPhone(e.target.value)}
                    className="w-full glass-input p-3 rounded-lg text-sm"
                  />
                </div>
                
                <div className="flex flex-col sm:flex-row gap-4 pt-4">
                  <button
                    type="submit"
                    className="flex-1 bg-purple-600 hover:bg-purple-700 text-white font-bold p-3 rounded-lg text-sm transition-all"
                  >
                    Send Invite & Continue
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMaxAllowedStep(7);
                      setCurrentStep(7);
                    }}
                    className="bg-transparent hover:bg-white/5 border border-white/10 text-zinc-400 font-bold py-3 px-6 rounded-lg text-sm transition-all"
                  >
                    Skip
                  </button>
                </div>
              </form>
            )}

            {/* STEP 7: WEBSITE WIDGET */}
            {currentStep === 7 && (
              <div className="space-y-6">
                <p className="text-zinc-400 text-sm text-center">
                  Copy this HTML script snippet and paste it onto your marketing website to embed the AI-powered online customer booking widget.
                </p>
                <div className="relative">
                  <pre className="bg-[#030303]/80 border border-white/5 p-4 rounded-lg text-[11px] font-mono text-zinc-300 overflow-x-auto select-all max-h-[140px] leading-relaxed">
                    {`<!-- Augmented Trade Tech Booking Widget -->\n<div id="att-booking-widget" data-company-id="${user?.company_id || "COMPANY_ID"}"></div>\n<script src="https://cdn.augmentedtradetech.com/widget.js" async></script>`}
                  </pre>
                  
                  <button
                    type="button"
                    onClick={copyWidgetCode}
                    className={`absolute top-2 right-2 px-3 py-1.5 rounded text-xs font-bold transition-all ${
                      widgetCopied
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/20"
                        : "bg-purple-600/20 text-purple-400 border border-purple-500/20 hover:bg-purple-600/30"
                    }`}
                  >
                    {widgetCopied ? "Copied!" : "Copy Code"}
                  </button>
                </div>

                <button
                  onClick={handleWidgetNext}
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white font-bold p-3 rounded-lg text-sm transition-all mt-4"
                >
                  Continue to Completion
                </button>
              </div>
            )}

            {/* STEP 8: COMPLETE */}
            {currentStep === 8 && (
              <div className="space-y-6 text-center py-8 relative">
                {/* Simulated CSS Confetti particles */}
                <div className="absolute inset-0 pointer-events-none flex justify-center items-center overflow-hidden">
                  <svg className="w-full h-full opacity-60" viewBox="0 0 400 300">
                    <circle cx="50" cy="50" r="4" fill="#9333ea" className="animate-bounce" style={{ animationDelay: "0.2s" }} />
                    <rect x="320" y="40" width="8" height="8" fill="#ec4899" className="animate-bounce" style={{ animationDelay: "0.5s" }} />
                    <circle cx="80" cy="220" r="5" fill="#3b82f6" className="animate-bounce" style={{ animationDelay: "0.8s" }} />
                    <rect x="290" y="240" width="6" height="12" fill="#10b981" className="animate-bounce" style={{ animationDelay: "0.1s" }} />
                  </svg>
                </div>

                <div className="w-20 h-20 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-6 shadow-xl shadow-emerald-500/5">
                  <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                
                <h3 className="text-2xl font-black text-white bg-gradient-to-r from-purple-400 to-indigo-400 bg-clip-text text-transparent">
                  Congratulations!
                </h3>
                <p className="text-zinc-400 text-sm max-w-md mx-auto leading-relaxed">
                  Your field operations platform is configured and ready. You can now start scheduling work orders, dispatching technicians, and accepting field payments.
                </p>

                <div className="pt-6">
                  <button
                    onClick={handleFinishOnboarding}
                    className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white font-bold py-3 px-10 rounded-lg text-sm transition-all shadow-lg shadow-purple-600/20"
                  >
                    Go to Operations Dashboard
                  </button>
                </div>
              </div>
            )}

          </div>

          {/* Navigation Controls footer */}
          <div className="flex items-center justify-between mt-8 pt-4 border-t border-white/5">
            {currentStep > 1 && currentStep < 8 ? (
              <button
                type="button"
                onClick={() => setCurrentStep(currentStep - 1)}
                className="flex items-center gap-2 text-zinc-400 hover:text-white transition-all text-xs font-semibold"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back to {STEPS[currentStep - 2].title}
              </button>
            ) : (
              <div />
            )}

            {currentStep < maxAllowedStep && currentStep < 8 ? (
              <button
                type="button"
                onClick={() => setCurrentStep(currentStep + 1)}
                className="flex items-center gap-2 text-purple-400 hover:text-purple-300 transition-all text-xs font-semibold"
              >
                Forward to {STEPS[currentStep].title}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            ) : (
              <div />
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
