export type Severity = 'P0' | 'P1' | 'P2' | 'P3' | 'P4';
export type IncidentStatus =
  | 'received'
  | 'triaging'
  | 'triaged'
  | 'ticket_created'
  | 'notified'
  | 'resolved'
  | 'failed';
export type TeamName =
  | 'backend'
  | 'frontend'
  | 'payments'
  | 'infrastructure'
  | 'database'
  | 'unknown';

export interface Incident {
  id: string;
  title: string;
  description: string;
  reporter_name: string;
  reporter_email: string;
  status: IncidentStatus;
  severity_hint: Severity | null;
  severity_final: Severity | null;
  assigned_team: TeamName | null;
  triage_summary: string | null;
  affected_components: string[];
  root_cause_hint: string | null;
  recommended_actions: string[];
  linear_ticket_id: string | null;
  linear_ticket_url: string | null;
  linear_ticket_identifier: string | null;
  attachments: string[];
  created_at: string;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  stage: string;
  message: string;
  success: boolean;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface CreateIncidentForm {
  title: string;
  description: string;
  reporter_name: string;
  reporter_email: string;
  severity_hint?: Severity;
  attachments?: File[];
}

export interface Stats {
  incidents_by_status: Record<string, number>;
  total: number;
}
