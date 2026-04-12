export type CisternAlert = {
  severity: "info" | "warning" | "error";
  code: string;
  message: string;
};

export type CisternSettings = {
  tank_height_ft: number;
  tank_diameter_ft: number;
  tank_full_gal: number;
  baseline_pct: number;
  baseline_ts: string | null;
  measurement_smoothing: number;
  fill_threshold_gal_hr: number;
  data_timeout_minutes: number;
  measurement_interval_minutes: number;
  sensor_offset_in: number;
  haul_tank_gal: number;
  low_alert_pct: number;
  target_pct: number;
  force_baseline: number;
};

export type CisternStatus = {
  last_ts: string | null;
  packet: string | null;
  adc: number | null;
  cal: number | null;
  age_seconds: number | null;
  last_reading_age_seconds: number | null;
  level_percent: number | null;
  volume_imp_gal: number | null;
  avg_daily_use_imp_gal: number | null;
  days_to_empty: number | null;
  baseline_age_days: number | null;
  display_mode: string;
  alerts: CisternAlert[];
  settings: CisternSettings;
};

export type HistoryPoint = {
  day: string;
  gal_used: number | null;
  samples: number;
};

export type LevelHistoryPoint = {
  day: string;
  ts: string;
  level_percent: number | null;
  volume_imp_gal: number | null;
};

export type HistoryResponse = {
  days: number;
  usage: HistoryPoint[];
  level_history: LevelHistoryPoint[];
};
