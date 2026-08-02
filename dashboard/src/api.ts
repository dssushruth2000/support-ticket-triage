export type MetricsSummary = {
  ticket_count: number;
  avg_cost_usd: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  escalation_rate: number;
  auto_respond_rate: number;
  draft_rate: number;
  cheap_tier_share: number;
  strong_tier_share: number;
  by_category: Record<string, number>;
  by_action: Record<string, number>;
  by_tier: Record<string, number>;
};

export type RecentTicket = {
  id: number;
  subject: string;
  category: string | null;
  action: string | null;
  confidence: number | null;
  cost_usd: number;
  latency_ms: number;
  model_tier: string | null;
  model_name: string | null;
  created_at: string;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function fetchSummary() {
  return getJson<MetricsSummary>("/metrics/summary");
}

export function fetchRecent(limit = 20) {
  return getJson<RecentTicket[]>(`/metrics/recent?limit=${limit}`);
}
