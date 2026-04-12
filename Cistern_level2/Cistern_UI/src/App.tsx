import { useEffect, useState } from "react";
import { Bell, Droplets, History, Settings } from "lucide-react";
import { OverviewDashboard } from "./components/OverviewDashboard";
import { SetupCalibration } from "./components/SetupCalibration";
import { HistoryUsage } from "./components/HistoryUsage";
import { AlertsAutomation } from "./components/AlertsAutomation";
import { fetchStatus } from "./api";
import type { CisternStatus } from "./types";

type Page = "overview" | "setup" | "history" | "alerts";

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("overview");
  const [status, setStatus] = useState<CisternStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      const next = await fetchStatus();
      setStatus(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadStatus();
    const interval = window.setInterval(() => {
      void loadStatus();
    }, 5000);
    return () => window.clearInterval(interval);
  }, []);

  const navigation = [
    { id: "overview", label: "Overview", icon: Droplets },
    { id: "setup", label: "Setup & Calibration", icon: Settings },
    { id: "history", label: "History & Usage", icon: History },
    { id: "alerts", label: "Alerts & Automation", icon: Bell },
  ] satisfies Array<{ id: Page; label: string; icon: typeof Droplets }>;

  const renderPage = () => {
    if (!status) {
      return (
        <div className="p-6 lg:p-8">
          <div className="rounded-xl border bg-white p-6 text-sm text-gray-600">
            {loading ? "Loading live cistern data..." : error ?? "No status available."}
          </div>
        </div>
      );
    }

    switch (currentPage) {
      case "overview":
        return <OverviewDashboard status={status} onRefresh={loadStatus} />;
      case "setup":
        return <SetupCalibration status={status} onRefresh={loadStatus} />;
      case "history":
        return <HistoryUsage status={status} />;
      case "alerts":
        return <AlertsAutomation status={status} onRefresh={loadStatus} />;
      default:
        return <OverviewDashboard status={status} onRefresh={loadStatus} />;
    }
  };

  const statusText = !status
    ? "Loading"
    : status.last_reading_age_seconds != null && status.last_reading_age_seconds < (status.settings.data_timeout_minutes * 60)
      ? "Online"
      : "Stale";

  return (
    <div className="flex h-screen bg-gray-50">
      <div className="hidden lg:flex w-64 bg-white border-r border-gray-200 flex-col">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Droplets className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-gray-900">Cistern Monitor</h1>
              <p className="text-sm text-gray-500">Live UI at /ui2</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-4">
          <ul className="space-y-1">
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = currentPage === item.id;
              return (
                <li key={item.id}>
                  <button
                    onClick={() => setCurrentPage(item.id)}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                      isActive ? "bg-blue-50 text-blue-700" : "text-gray-700 hover:bg-gray-100"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="font-medium">{item.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="p-4 border-t border-gray-200 text-xs text-gray-500">
          <div className="flex items-center justify-between mb-1">
            <span>System Status</span>
            <span className="inline-flex items-center gap-1">
              <span
                className={`w-2 h-2 rounded-full ${statusText === "Online" ? "bg-green-500" : "bg-yellow-500"}`}
              />
              {statusText}
            </span>
          </div>
          <div className="text-gray-400">
            Last update: {status?.last_ts ?? "No readings yet"}
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto pb-20 lg:pb-0">
        <div className="lg:hidden sticky top-0 z-10 bg-white border-b border-gray-200 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <Droplets className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="font-semibold text-gray-900">Cistern Monitor</h1>
              <p className="text-xs text-gray-500">Live UI at /ui2</p>
            </div>
          </div>
        </div>

        {error && !status ? (
          <div className="p-6 lg:p-8">
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          </div>
        ) : null}

        {renderPage()}
      </div>

      <div className="lg:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 px-2 py-2 z-20">
        <nav className="flex items-center justify-around">
          {navigation.map((item) => {
            const Icon = item.icon;
            const isActive = currentPage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setCurrentPage(item.id)}
                className={`flex flex-col items-center gap-1 px-3 py-2 rounded-lg transition-colors min-w-0 flex-1 ${
                  isActive ? "text-blue-700" : "text-gray-600"
                }`}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="text-xs font-medium truncate w-full text-center">
                  {item.id === "setup" ? "Setup" : item.id === "history" ? "History" : item.id === "alerts" ? "Alerts" : item.label}
                </span>
              </button>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
