import { useEffect, useState } from "react";
import { AlertTriangle, Bell, Clock, Save } from "lucide-react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { saveSettings } from "../api";
import type { CisternStatus } from "../types";

type Props = {
  status: CisternStatus;
  onRefresh: () => Promise<void>;
};

export function AlertsAutomation({ status, onRefresh }: Props) {
  const [lowAlertPct, setLowAlertPct] = useState(status.settings.low_alert_pct);
  const [timeoutMinutes, setTimeoutMinutes] = useState(status.settings.data_timeout_minutes);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setLowAlertPct(status.settings.low_alert_pct);
    setTimeoutMinutes(status.settings.data_timeout_minutes);
  }, [status.settings.data_timeout_minutes, status.settings.low_alert_pct]);

  const handleSave = async () => {
    try {
      await saveSettings({
        low_alert_pct: lowAlertPct,
        data_timeout_minutes: timeoutMinutes,
      });
      setMessage("Saved alert thresholds to the backend settings store.");
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save alert settings.");
    }
  };

  const alerts = status.alerts ?? [];

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mb-6 lg:mb-8">
        <h2 className="text-2xl sm:text-3xl font-semibold text-gray-900 mb-2">Alerts & Automation</h2>
        <p className="text-sm sm:text-base text-gray-600">Live alerts from Flask plus threshold settings stored in SQLite</p>
      </div>

      {message ? (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {message}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className="lg:col-span-2 space-y-4 sm:space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Active Alerts</h3>
            <div className="text-sm text-gray-500">{alerts.length} active</div>
          </div>

          <div className="space-y-4">
            {alerts.length === 0 ? (
              <Card className="p-6">
                <div className="text-sm text-gray-600">No active alerts from the live backend.</div>
              </Card>
            ) : (
              alerts.map((alert) => (
                <Card key={alert.code} className="p-4 sm:p-6">
                  <div className="flex items-start gap-4">
                    <div
                      className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                        alert.severity === "error"
                          ? "bg-red-100"
                          : alert.severity === "warning"
                            ? "bg-yellow-100"
                            : "bg-blue-100"
                      }`}
                    >
                      <AlertTriangle
                        className={`w-6 h-6 ${
                          alert.severity === "error"
                            ? "text-red-600"
                            : alert.severity === "warning"
                              ? "text-yellow-600"
                              : "text-blue-600"
                        }`}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-gray-900 mb-1">{alert.code}</div>
                      <div className="text-sm text-gray-600">{alert.message}</div>
                    </div>
                  </div>
                </Card>
              ))
            )}
          </div>

          <Card className="p-4 sm:p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Backend Alert Thresholds</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="lowAlertPct">Low Level Threshold (%)</Label>
                <Input
                  id="lowAlertPct"
                  type="number"
                  value={lowAlertPct}
                  onChange={(e) => setLowAlertPct(Number(e.target.value))}
                  className="mt-1.5"
                />
              </div>
              <div>
                <Label htmlFor="timeoutMinutes">Stale Data Timeout (minutes)</Label>
                <Input
                  id="timeoutMinutes"
                  type="number"
                  value={timeoutMinutes}
                  onChange={(e) => setTimeoutMinutes(Number(e.target.value))}
                  className="mt-1.5"
                />
              </div>
            </div>

            <Button onClick={() => void handleSave()} className="mt-4 bg-blue-600 hover:bg-blue-700">
              <Save className="w-4 h-4 mr-2" />
              Save Thresholds
            </Button>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Rule Summary</h3>
            <div className="space-y-4 text-sm">
              <div className="flex items-start gap-3">
                <Bell className="w-5 h-5 text-gray-600 mt-0.5" />
                <div>
                  <div className="font-medium text-gray-900">Low Water Alert</div>
                  <div className="text-gray-600">Triggers below {status.settings.low_alert_pct}%.</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Clock className="w-5 h-5 text-gray-600 mt-0.5" />
                <div>
                  <div className="font-medium text-gray-900">Stale Data Alert</div>
                  <div className="text-gray-600">Triggers after {status.settings.data_timeout_minutes} minutes without a reading.</div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-gray-600 mt-0.5" />
                <div>
                  <div className="font-medium text-gray-900">Baseline Age Notice</div>
                  <div className="text-gray-600">Shown when the saved baseline gets old.</div>
                </div>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Current State</h3>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Current Level</span>
                <span className="font-medium text-gray-900">
                  {status.level_percent != null ? `${status.level_percent.toFixed(1)}%` : "No data"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Current Volume</span>
                <span className="font-medium text-gray-900">
                  {status.volume_imp_gal != null ? `${Math.round(status.volume_imp_gal)} imp gal` : "No data"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Last Reading Age</span>
                <span className="font-medium text-gray-900">
                  {status.last_reading_age_seconds != null ? `${status.last_reading_age_seconds} sec` : "No data"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Baseline Age</span>
                <span className="font-medium text-gray-900">
                  {status.baseline_age_days != null ? `${status.baseline_age_days} days` : "Not set"}
                </span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
