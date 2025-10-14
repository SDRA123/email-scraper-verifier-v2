export interface User {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  username: string;
  email: string;
  password: string;
}

export interface EmailData {
  id?: number;
  email: string;
  name?: string;
  company?: string;
  website?: string;
  verified?: boolean;
  status?: string;
  is_blog?: boolean;
  blog_score?: number;
  blog_notes?: string;
  verification_quality?: number;
  verification_status?: string;
  verification_notes?: string;
  source?: string;
  created_at?: string;
  upload_id?: number;
  row_id?: string;

  // Multiple emails
  email_2?: string;
  email_3?: string;
  email_2_verified?: boolean;
  email_3_verified?: boolean;
  email_2_quality?: number;
  email_3_quality?: number;

  // Social media links
  linkedin?: string;
  instagram?: string;
  facebook?: string;
  contact_form?: string;

  // Email campaign tracking
  email_sent?: boolean;
  email_sent_date?: string;

  // Additional metadata
  phone?: string;
  job_title?: string;
  notes?: string;
}

export interface ExcelUploadResponse {
  message: string;
  data_id: number;
  processed_count: number;
}

export interface VerificationResult {
  email: string;
  is_valid: boolean;
  quality?: number;
  status?: string;
  notes?: string;
}

export interface PipelineResponse {
  process_id: string;
  message: string;
  data_id?: number;
}

export interface BlogCheckResponse {
  total_websites?: number;
  blogs_found?: number;
  recent_content_found?: number;
  updated_records?: number;
  process_id?: string;
  message?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface DashboardEntrySummary {
  website: string;
  upload_ids: number[];
  email_count: number;
  last_upload: string | null;
}

export interface DashboardEmailSummary {
  email: string;
  website?: string;
  company?: string;
  verified?: boolean;
  quality?: number;
  status?: string;
  notes?: string;
  source?: string;
  upload_ids?: number[];
  last_seen?: string | null;
}

export interface DashboardSummary {
  total_uploads: number;
  total_entries: number;
  total_emails: number;
  verified_emails: number;
  invalid_emails: number;
  pending_emails: number;
  entries: DashboardEntrySummary[];
  emails: DashboardEmailSummary[];
  verified_list: DashboardEmailSummary[];
  invalid_list: DashboardEmailSummary[];
}