"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "../../../hooks/useAuth";
import { AuthGuard } from "../../../components/AuthGuard";
import { InviteMemberModal } from "../../../components/InviteMemberModal";
import { EditMemberModal } from "../../../components/EditMemberModal";
import { DeactivateConfirmDialog } from "../../../components/DeactivateConfirmDialog";
import { 
  Users, 
  Plus, 
  Mail, 
  Phone, 
  ShieldAlert, 
  Edit2, 
  UserMinus, 
  Loader2, 
  ArrowLeft,
  CheckCircle,
  Clock,
  Sparkles
} from "lucide-react";

export default function TeamSettingsPage() {
  return (
    <AuthGuard>
      <TeamSettingsContent />
    </AuthGuard>
  );
}

function TeamSettingsContent() {
  const { accessToken, user } = useAuth();
  const [team, setTeam] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal open states
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isDeactivateOpen, setIsDeactivateOpen] = useState(false);

  // Selected member states
  const [selectedMember, setSelectedMember] = useState<any | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const fetchTeam = async () => {
    setIsLoading(true);
    setError(null);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const res = await fetch(`${API_URL}/users`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to load team members");
      }

      const data = await res.json();
      setTeam(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (accessToken) {
      fetchTeam();
    }
  }, [accessToken]);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);
  };

  const handleResendInvite = async (memberId: string) => {
    setResendingId(memberId);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    try {
      const res = await fetch(`${API_URL}/users/${memberId}/resend-invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Failed to resend invite");
      }

      showToast("Invitation link successfully resent!");
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    } finally {
      setResendingId(null);
    }
  };

  const openEdit = (member: any) => {
    setSelectedMember(member);
    setIsEditOpen(true);
  };

  const openDeactivate = (member: any) => {
    setSelectedMember(member);
    setIsDeactivateOpen(true);
  };

  // Check if current user is admin
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
            Only company administrators can access team settings.
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
        <div className="fixed bottom-8 right-8 z-50 flex items-center gap-2 px-5 py-3 rounded-xl glass-card border-indigo-500/30 text-white shadow-2xl text-sm font-medium animate-in fade-in slide-in-from-bottom-5">
          <CheckCircle className="w-4 h-4 text-emerald-400" />
          {toastMessage}
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
            Team Settings
          </h1>
          <p className="text-sm text-slate-400">
            Manage your company technicians, dispatchers, and access privileges.
          </p>
        </div>
        <button 
          onClick={() => setIsInviteOpen(true)} 
          className="flex items-center gap-2 px-5 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 active:scale-[0.98] text-white font-bold text-sm rounded-xl cursor-pointer shadow-lg shadow-indigo-500/10 transition-all duration-200"
        >
          <Plus className="w-4 h-4" />
          Invite Team Member
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table Section */}
      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-4">
          <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
          <span className="text-sm text-slate-400 font-medium">Retrieving team roster...</span>
        </div>
      ) : (
        <div className="glass-card rounded-2xl overflow-hidden shadow-2xl relative">
          <div className="absolute top-0 right-0 w-60 h-60 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-white/5 bg-slate-950/40">
                  <th className="px-6 py-4.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Name / Email</th>
                  <th className="px-6 py-4.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Role</th>
                  <th className="px-6 py-4.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Trades / Status</th>
                  <th className="px-6 py-4.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider">Last Login</th>
                  <th className="px-6 py-4.5 text-[11px] font-bold text-slate-400 uppercase tracking-wider text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {team.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-12 text-center text-sm text-slate-500">
                      No team members found. Click "Invite Team Member" to get started.
                    </td>
                  </tr>
                ) : (
                  team.map((member) => {
                    const isUserActive = member.is_active;
                    const isInvited = !isUserActive && !member.last_login_at;

                    return (
                      <tr key={member.id} className="hover:bg-white/5 transition-colors">
                        <td className="px-6 py-4.5 whitespace-nowrap">
                          <div className="flex flex-col gap-0.5">
                            <span className="font-bold text-sm text-white">
                              {member.full_name || <span className="text-slate-500 italic font-normal">Pending Invitation</span>}
                            </span>
                            <span className="text-xs text-slate-500 flex items-center gap-1">
                              <Mail className="w-3 h-3 text-slate-600" />
                              {member.email}
                            </span>
                            {member.phone && (
                              <span className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                                <Phone className="w-3 h-3 text-slate-650" />
                                {member.phone}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4.5 whitespace-nowrap">
                          <span className={`inline-flex px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                            member.role === "company_admin" ? "bg-purple-500/10 border-purple-500/20 text-purple-300" :
                            member.role === "dispatcher" ? "bg-blue-500/10 border-blue-500/20 text-blue-300" :
                            "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
                          }`}>
                            {member.role === "company_admin" ? "Admin" :
                             member.role === "dispatcher" ? "Dispatcher" :
                             "Technician"}
                          </span>
                        </td>
                        <td className="px-6 py-4.5">
                          {member.role === "tech" && member.tech_profile ? (
                            <div className="flex flex-col gap-2">
                              <div className="flex flex-wrap gap-1">
                                {member.tech_profile.trades && member.tech_profile.trades.length > 0 ? (
                                  member.tech_profile.trades.map((t: string) => (
                                    <span key={t} className="px-1.5 py-0.5 bg-slate-800/80 border border-slate-700/60 rounded text-[9px] font-bold text-slate-300 uppercase">
                                      {t.replace("_", " ")}
                                    </span>
                                  ))
                                ) : (
                                  <span className="text-[10px] text-slate-500">No trades assigned</span>
                                )}
                              </div>
                              <div className="flex items-center gap-1.5">
                                <div className={`w-1.5 h-1.5 rounded-full ${
                                  member.tech_profile.availability_status === "available" ? "bg-emerald-500" :
                                  member.tech_profile.availability_status === "on_job" ? "bg-blue-500" :
                                  member.tech_profile.availability_status === "driving" ? "bg-purple-500" :
                                  member.tech_profile.availability_status === "break" ? "bg-amber-500" :
                                  member.tech_profile.availability_status === "off_duty" ? "bg-slate-500" : "bg-red-500"
                                }`} />
                                <span className="text-[10px] text-slate-400 capitalize">
                                  {member.tech_profile.availability_status}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-700">&mdash;</span>
                          )}
                        </td>
                        <td className="px-6 py-4.5 whitespace-nowrap text-xs text-slate-400">
                          {isInvited ? (
                            <span className="text-amber-500 font-semibold flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5" />
                              Invited (Pending)
                            </span>
                          ) : member.last_login_at ? (
                            new Date(member.last_login_at).toLocaleString()
                          ) : (
                            <span className="text-slate-600">Never logged in</span>
                          )}
                        </td>
                        <td className="px-6 py-4.5 whitespace-nowrap text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => openEdit(member)}
                              className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-750 hover:border-slate-650 rounded-lg text-xs font-semibold text-slate-300 hover:text-white cursor-pointer transition-colors"
                              title="Edit Team Member"
                            >
                              <Edit2 className="w-3 h-3" />
                              Edit
                            </button>
                            
                            {isInvited && (
                              <button
                                onClick={() => handleResendInvite(member.id)}
                                className="inline-flex items-center gap-1 px-3 py-1.5 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/25 rounded-lg text-xs font-semibold text-indigo-400 hover:text-indigo-350 cursor-pointer transition-colors disabled:opacity-50"
                                disabled={resendingId === member.id}
                                title="Resend Invite"
                              >
                                {resendingId === member.id ? "Sending..." : "Resend"}
                              </button>
                            )}

                            {member.id !== user?.id && isUserActive && (
                              <button
                                onClick={() => openDeactivate(member)}
                                className="inline-flex items-center gap-1 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/25 rounded-lg text-xs font-semibold text-red-400 hover:text-red-350 cursor-pointer transition-colors"
                                title="Deactivate Member"
                              >
                                <UserMinus className="w-3 h-3" />
                                Deactivate
                              </button>
                            )}

                            {!isUserActive && !isInvited && (
                              <span className="text-xs text-red-400/80 font-bold italic px-2">
                                Deactivated
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modals */}
      <InviteMemberModal
        isOpen={isInviteOpen}
        onClose={() => setIsInviteOpen(false)}
        onSuccess={fetchTeam}
      />

      <EditMemberModal
        isOpen={isEditOpen}
        member={selectedMember}
        onClose={() => setIsEditOpen(false)}
        onSuccess={fetchTeam}
      />

      <DeactivateConfirmDialog
        isOpen={isDeactivateOpen}
        member={selectedMember}
        onClose={() => setIsDeactivateOpen(false)}
        onSuccess={fetchTeam}
      />
    </div>
  );
}
