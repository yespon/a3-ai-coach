export interface WhitelistEntry {
  id: string;
  employee_no: string;
  email: string | null;
  enabled: boolean;
  source: "manual" | "excel" | string;
  created_at: string;
  updated_at: string;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; reason: string }[];
}
