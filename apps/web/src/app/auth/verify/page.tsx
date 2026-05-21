"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../../../hooks/useAuth";
import Link from "next/link";

function VerifyContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const { verifyMagicLink } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError("No token was found in this login link.");
      return;
    }

    const performVerification = async () => {
      try {
        await verifyMagicLink(token);
      } catch (err: any) {
        setError(err.message || "This login link is invalid, expired, or has already been used.");
      }
    };

    performVerification();
  }, [token, verifyMagicLink]);

  if (error) {
    return (
      <div style={cardStyle}>
        <h2 style={errorTitleStyle}>Login Failed</h2>
        <p style={errorTextStyle}>{error}</p>
        <Link href="/login" style={buttonStyle}>
          Return to Sign In
        </Link>
      </div>
    );
  }

  return (
    <div style={cardStyle}>
      <div style={spinnerStyle}></div>
      <h2 style={titleStyle}>Authenticating</h2>
      <p style={textStyle}>Setting up your secure session, please wait...</p>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <div style={containerStyle}>
      <Suspense
        fallback={
          <div style={cardStyle}>
            <div style={spinnerStyle}></div>
            <h2 style={titleStyle}>Loading...</h2>
          </div>
        }
      >
        <VerifyContent />
      </Suspense>
    </div>
  );
}

// Styling (aligns with the premium Login Page aesthetic)
const containerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  minHeight: "100vh",
  background: "linear-gradient(135deg, #020617 0%, #0f172a 50%, #1e1b4b 100%)",
  fontFamily: "'Outfit', 'Inter', sans-serif",
  color: "#f8fafc",
  padding: "1rem",
};

const cardStyle: React.CSSProperties = {
  width: "100%",
  maxWidth: "420px",
  padding: "2.5rem",
  borderRadius: "1.5rem",
  backgroundColor: "rgba(15, 23, 42, 0.45)",
  backdropFilter: "blur(16px)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  textAlign: "center",
};

const spinnerStyle: React.CSSProperties = {
  width: "50px",
  height: "50px",
  border: "4px solid rgba(99, 102, 241, 0.1)",
  borderTop: "4px solid #6366f1",
  borderRadius: "50%",
  animation: "spin 1s linear infinite",
};

const titleStyle: React.CSSProperties = {
  fontSize: "1.5rem",
  fontWeight: 700,
  marginTop: "1.5rem",
  marginBottom: "0.5rem",
  background: "linear-gradient(to right, #818cf8, #c084fc)",
  WebkitBackgroundClip: "text",
  WebkitTextFillColor: "transparent",
};

const textStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  color: "#94a3b8",
  margin: 0,
  lineHeight: "1.5",
};

const errorTitleStyle: React.CSSProperties = {
  fontSize: "1.5rem",
  fontWeight: 700,
  color: "#fca5a5",
  margin: 0,
  marginBottom: "0.75rem",
};

const errorTextStyle: React.CSSProperties = {
  fontSize: "0.95rem",
  color: "#cbd5e1",
  marginBottom: "1.5rem",
  lineHeight: "1.5",
  margin: "0 0 1.5rem 0",
};

const buttonStyle: React.CSSProperties = {
  padding: "0.75rem 1.5rem",
  borderRadius: "0.75rem",
  backgroundColor: "#6366f1",
  color: "#ffffff",
  fontSize: "0.95rem",
  fontWeight: 600,
  textDecoration: "none",
  transition: "background-color 0.2s",
  display: "inline-block",
  boxShadow: "0 4px 6px -1px rgba(99, 102, 241, 0.4)",
};

// Inject keyframe animation dynamically
if (typeof window !== "undefined") {
  const style = document.createElement("style");
  style.innerHTML = `
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    a:hover {
      background-color: #4f46e5 !important;
    }
  `;
  document.head.appendChild(style);
}
