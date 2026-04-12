import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download } from "lucide-react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { fetchHistory, postAction } from "../api";
import type { CisternStatus, HistoryResponse } from "../types";

type Props = {
  status: CisternStatus;
};

export function HistoryUsage({ status }: Props) {
  const [timeRange, setTimeRange] = useState<7 | 30 | 90 | 365>(30);
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    const load = async () => {
      try {
        const result = await fetchHistory(timeRange);
        if (!ignore) {
          setHistory(result);
          setError(null);
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : "Failed to load history.");
        }
      }
    };

    void load();
    return () => {
      ignore = true;
    };
  }, [timeRange]);

  const usageRows = history?.usage ?? [];
  const levelRows = history?.level_history ?? [];
  const usageValues = usageRows.map((row) => row.gal_used ?? 0);
  const totalUsage = usageValues.reduce((sum, value) => sum + value, 0);
  const avgUsage = usageValues.length ? totalUsage / usageValues.length : null;
  const maxUsage = usageValues.length ? Math.max(...usageValues) : null;
  const minUsage = usageValues.length ? Math.min(...usageValues) : null;

  const exportData = async () => {
    const result = await postAction<{ ok: boolean; download_url: string }>("/api/export_logs");
    window.location.assign(result.download_url);
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mb-6 lg:mb-8 flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-semibold text-gray-900 mb-2">History & Usage</h2>
          <p className="text-sm sm:text-base text-gray-600">Live usage history computed from the existing SQLite data</p>
        </div>
        <Button onClick={() => void exportData()} variant="outline">
          <Download className="w-4 h-4 mr-2" />
          Export Data
        </Button>
      </div>

      <div className="mb-4 sm:mb-6 flex gap-2 overflow-x-auto pb-2">
        {[
          { value: 7 as const, label: "Last 7 Days" },
          { value: 30 as const, label: "Last 30 Days" },
          { value: 90 as const, label: "Last 90 Days" },
          { value: 365 as const, label: "Last Year" },
        ].map((range) => (
          <Button
            key={range.value}
            variant={timeRange === range.value ? "default" : "outline"}
            onClick={() => setTimeRange(range.value)}
            className={timeRange === range.value ? "bg-blue-600 hover:bg-blue-700" : ""}
          >
            {range.label}
          </Button>
        ))}
      </div>

      {error ? (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-6">
        <Card className="p-6">
          <div className="text-sm text-gray-600 mb-1">Total Usage</div>
          <div className="text-2xl font-semibold text-gray-900">{Math.round(totalUsage).toLocaleString()} gal</div>
          <div className="text-sm text-gray-500 mt-1">Range: last {timeRange} days</div>
        </Card>

        <Card className="p-6">
          <div className="text-sm text-gray-600 mb-1">Daily Average</div>
          <div className="text-2xl font-semibold text-gray-900">
            {avgUsage != null ? `${avgUsage.toFixed(1)} gal` : "No data"}
          </div>
          <div className="text-sm text-gray-500 mt-1">Current forecast: {status.days_to_empty != null ? `${status.days_to_empty.toFixed(1)} days to empty` : "Unavailable"}</div>
        </Card>

        <Card className="p-6">
          <div className="text-sm text-gray-600 mb-1">Peak Day</div>
          <div className="text-2xl font-semibold text-gray-900">{maxUsage != null ? `${Math.round(maxUsage)} gal` : "No data"}</div>
          <div className="text-sm text-gray-500 mt-1">Largest daily usage in this range</div>
        </Card>

        <Card className="p-6">
          <div className="text-sm text-gray-600 mb-1">Lowest Day</div>
          <div className="text-2xl font-semibold text-gray-900">{minUsage != null ? `${Math.round(minUsage)} gal` : "No data"}</div>
          <div className="text-sm text-gray-500 mt-1">Smallest daily usage in this range</div>
        </Card>
      </div>

      <Card className="p-6 mb-6">
        <h3 className="font-semibold text-gray-900 mb-4">Water Level History</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={levelRows}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="day" stroke="#6b7280" />
            <YAxis stroke="#6b7280" />
            <Tooltip />
            <Line
              type="monotone"
              dataKey="level_percent"
              stroke="#2563eb"
              strokeWidth={2}
              name="Water Level (%)"
              dot={{ fill: "#2563eb", r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card className="p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Daily Usage</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={usageRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="day" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip />
              <Bar dataKey="gal_used" fill="#10b981" name="Usage (imp gal)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-6">
          <h3 className="font-semibold text-gray-900 mb-4">Daily Samples</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={usageRows}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="day" stroke="#6b7280" />
              <YAxis stroke="#6b7280" />
              <Tooltip />
              <Bar dataKey="samples" fill="#8b5cf6" name="Readings per day" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card className="p-6">
        <h3 className="font-semibold text-gray-900 mb-4">Usage Insights</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="font-medium text-gray-900 mb-1">Current Remaining Volume</div>
            <div className="text-gray-600">
              {status.volume_imp_gal != null ? `${Math.round(status.volume_imp_gal)} imperial gallons remain.` : "No live volume available."}
            </div>
          </div>

          <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
            <div className="font-medium text-gray-900 mb-1">Average Daily Use</div>
            <div className="text-gray-600">
              {status.avg_daily_use_imp_gal != null ? `${status.avg_daily_use_imp_gal.toFixed(1)} imperial gallons per day.` : "Not enough usage data yet."}
            </div>
          </div>

          <div className="p-4 bg-green-50 rounded-lg border border-green-200">
            <div className="font-medium text-gray-900 mb-1">Current Level</div>
            <div className="text-gray-600">
              {status.level_percent != null ? `${status.level_percent.toFixed(1)}% full.` : "No live level available."}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
