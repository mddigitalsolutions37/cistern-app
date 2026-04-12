import type { CisternSettings, CisternStatus, HistoryResponse } from "./types";

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchStatus(): Promise<CisternStatus> {
  return parseJson<CisternStatus>(await fetch("/api/status"));
}

export async function fetchHistory(days: number): Promise<HistoryResponse> {
  return parseJson<HistoryResponse>(await fetch(`/api/ui2/history?days=${days}`));
}

export async function saveSettings(settings: Partial<CisternSettings>) {
  return parseJson<{ ok: boolean; settings: CisternSettings; interval_cmd_result: string | null }>(
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),
  );
}

export async function postAction<T = { result?: string; ok?: boolean }>(
  url: string,
  body?: Record<string, unknown>,
): Promise<T> {
  return parseJson<T>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),
  );
}
