export type Severity = "P0" | "P1" | "P2" | "P3";
export type IncidentState = "OPEN" | "INVESTIGATING" | "RESOLVED" | "CLOSED";
export type ComponentKind = "RDBMS" | "MCP" | "API" | "CACHE" | "QUEUE" | "NOSQL";

export interface Incident {
  id: string;
  component_id: string;
  component_kind: ComponentKind;
  severity: Severity;
  state: IncidentState;
  title: string;
  first_signal_at: string;
  last_signal_at: string;
  closed_at?: string | null;
  mttr_seconds?: number | null;
  signal_count: number;
  summary?: string | null;
  has_rca: boolean;
}

export interface RawSignal {
  component_id: string;
  component_kind: string;
  severity: string;
  message: string;
  occurred_at?: string;
  created_at?: string;
  payload?: Record<string, unknown>;
  anomaly_score?: number | null;
  is_anomalous?: boolean;
}

export interface Comment {
  id: string;
  incident_id: string;
  author: string;
  body: string;
  parent_id?: string | null;
  created_at: string;
}

export interface Viewer {
  nickname: string;
  avatar_color: string;
}
