// Shared Types & Utilities
export interface UserContext {
  userId: string;
  companyId: string;
  role: string;
}

export function formatCents(cents: number): string {
  return (cents / 100).toFixed(2);
}
