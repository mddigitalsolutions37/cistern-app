import { Activity, AlertTriangle, Droplet, RefreshCw } from "lucide-react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import type { CisternStatus } from "../types";

type Props = {
  status: CisternStatus;
  onRefresh: () => Promise<void>;
};

export function OverviewDashboard({ status, onRefresh }: Props) {
  const level = status.level_percent ?? 0;
  const fillPercent = Math.max(0, Math.min(100, level));
  const volume = status.volume_imp_gal;
  const avgDaily = status.avg_daily_use_imp_gal;
  const daysToEmpty = status.days_to_empty;
  const alerts = status.alerts ?? [];

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mb-6 lg:mb-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl sm:text-3xl font-semibold text-gray-900 mb-2">Overview Dashboard</h2>
          <p className="text-sm sm:text-base text-gray-600">Live cistern readings from the existing bridge and Flask backend</p>
        </div>
        <Button variant="outline" onClick={() => void onRefresh()}>
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6 mb-4 sm:mb-6">
        <Card className="lg:col-span-2 p-4 sm:p-6 relative overflow-hidden min-h-[260px]">
          <div className="absolute inset-0 overflow-hidden">
            <div
              className="absolute inset-0 bg-gradient-to-br from-blue-500 via-blue-600 to-blue-700 transition-transform duration-700 ease-out"
              style={{ transform: `translateY(${100 - fillPercent}%)` }}
            />
            <div className="absolute inset-0 bg-gradient-to-t from-white/0 via-white/0 to-white/12 pointer-events-none" />
          </div>

          <div className="relative z-10 flex h-full flex-col justify-between">
            <div className="flex items-start justify-between mb-4 sm:mb-6">
              <div>
                <div className="text-sm text-gray-700 mb-1">Current Water Level</div>
                <div className="text-4xl sm:text-5xl font-bold mb-2 text-gray-900">
                  {status.level_percent != null ? `${status.level_percent.toFixed(1)}%` : "No data"}
                </div>
                <div className="text-sm sm:text-base text-gray-700">
                  {volume != null ? `${Math.round(volume).toLocaleString()} / ${Math.round(status.settings.tank_full_gal).toLocaleString()} imperial gallons` : "No volume available"}
                </div>
              </div>
              <div className="w-12 h-12 sm:w-16 sm:h-16 bg-white/70 rounded-full flex items-center justify-center">
                <Droplet className="w-6 h-6 sm:w-8 sm:h-8 text-blue-700" />
              </div>
            </div>

            <div className="text-xs sm:text-sm text-gray-700">
              Last reading: {status.last_ts ?? "No live reading yet"}
            </div>
          </div>
        </Card>

        <Card className="p-4 sm:p-6">
          <div className="mb-4">
            <div className="text-sm sm:text-base text-gray-600 mb-1">System Status</div>
            <div className="flex items-center gap-2">
              <span
                className={`w-3 h-3 rounded-full ${status.last_reading_age_seconds != null && status.last_reading_age_seconds < (status.settings.data_timeout_minutes * 60) ? "bg-green-500" : "bg-yellow-500"}`}
              />
              <span className="text-sm sm:text-base font-semibold text-gray-900">
                {status.last_reading_age_seconds != null && status.last_reading_age_seconds < (status.settings.data_timeout_minutes * 60) ? "Active & Monitoring" : "Waiting / Stale"}
              </span>
            </div>
          </div>

          <div className="space-y-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Display Mode</div>
              <div className="font-medium text-gray-900">{status.display_mode.replaceAll("_", " ")}</div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Last Reading Age</div>
              <div className="font-medium text-gray-900">
                {status.last_reading_age_seconds != null ? `${status.last_reading_age_seconds} sec` : "No data"}
              </div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Calibration</div>
              <div className="font-medium text-gray-900">{status.cal != null && status.cal >= 1 ? `CAL ${status.cal}` : "Baseline only"}</div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Baseline Age</div>
              <div className="font-medium text-gray-900">
                {status.baseline_age_days != null ? `${status.baseline_age_days} days` : "Not set"}
              </div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">ADC</div>
              <div className="font-medium text-gray-900">{status.adc ?? "No data"}</div>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-6 mb-4 sm:mb-6">
        <Card className="p-4 sm:p-6">
          <div className="flex items-start justify-between mb-3 sm:mb-4">
            <div className="w-10 h-10 sm:w-12 sm:h-12 bg-blue-100 rounded-lg flex items-center justify-center">
              <Activity className="w-5 h-5 sm:w-6 sm:h-6 text-blue-600" />
            </div>
            <span className="text-xs sm:text-sm text-gray-500">30 days</span>
          </div>
          <div className="text-xl sm:text-2xl font-semibold text-gray-900 mb-1">
            {avgDaily != null ? `${avgDaily.toFixed(1)} gal` : "No data"}
          </div>
          <div className="text-xs sm:text-sm text-gray-600">Average Daily Use</div>
        </Card>

        <Card className="p-4 sm:p-6">
          <div className="flex items-start justify-between mb-3 sm:mb-4">
            <div className="w-10 h-10 sm:w-12 sm:h-12 bg-green-100 rounded-lg flex items-center justify-center">
              <Droplet className="w-5 h-5 sm:w-6 sm:h-6 text-green-600" />
            </div>
            <span className="text-xs sm:text-sm text-gray-500">Current</span>
          </div>
          <div className="text-xl sm:text-2xl font-semibold text-gray-900 mb-1">
            {volume != null ? `${Math.round(volume)} gal` : "No data"}
          </div>
          <div className="text-xs sm:text-sm text-gray-600">Remaining Volume</div>
        </Card>

        <Card className="p-4 sm:p-6">
          <div className="flex items-start justify-between mb-3 sm:mb-4">
            <div className="w-10 h-10 sm:w-12 sm:h-12 bg-purple-100 rounded-lg flex items-center justify-center">
              <Droplet className="w-5 h-5 sm:w-6 sm:h-6 text-purple-600" />
            </div>
            <span className="text-xs sm:text-sm text-gray-500">Forecast</span>
          </div>
          <div className="text-xl sm:text-2xl font-semibold text-gray-900 mb-1">
            {daysToEmpty != null ? `${daysToEmpty.toFixed(1)} days` : "No data"}
          </div>
          <div className="text-xs sm:text-sm text-gray-600">Days To Empty</div>
        </Card>

        <Card className="p-4 sm:p-6">
          <div className="flex items-start justify-between mb-3 sm:mb-4">
            <div className="w-10 h-10 sm:w-12 sm:h-12 bg-yellow-100 rounded-lg flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 text-yellow-600" />
            </div>
            <span className="text-xs sm:text-sm text-gray-500">Live</span>
          </div>
          <div className="text-xl sm:text-2xl font-semibold text-gray-900 mb-1">{alerts.length}</div>
          <div className="text-xs sm:text-sm text-gray-600">Active Alerts</div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <Card className="p-4 sm:p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Current Reading</h3>
          <div className="space-y-3 text-sm">
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Packet</div>
              <div className="font-medium text-gray-900 break-all text-right">{status.packet ?? "No packet"}</div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Tank Height</div>
              <div className="font-medium text-gray-900">{status.settings.tank_height_ft} ft</div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Tank Diameter</div>
              <div className="font-medium text-gray-900">{status.settings.tank_diameter_ft} ft</div>
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="text-gray-600">Low Alert Threshold</div>
              <div className="font-medium text-gray-900">{status.settings.low_alert_pct}%</div>
            </div>
          </div>
        </Card>

        <Card className="p-4 sm:p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Active Alerts</h3>
          {alerts.length === 0 ? (
            <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800">
              No active alerts from the live backend.
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.code}
                  className={`flex items-start gap-3 p-3 rounded-lg border ${
                    alert.severity === "error"
                      ? "bg-red-50 border-red-200"
                      : alert.severity === "warning"
                        ? "bg-yellow-50 border-yellow-200"
                        : "bg-blue-50 border-blue-200"
                  }`}
                >
                  <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="text-sm font-medium text-gray-900">{alert.code}</div>
                    <div className="text-xs text-gray-600 mt-1">{alert.message}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
