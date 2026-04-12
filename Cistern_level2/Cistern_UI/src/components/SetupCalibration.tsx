import { useEffect, useState } from "react";
import { Download, Eye, RotateCcw, Save, Trash2, Wrench, X } from "lucide-react";
import { Card } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Slider } from "./ui/slider";
import { postAction, saveSettings } from "../api";
import type { CisternSettings, CisternStatus } from "../types";

type Props = {
  status: CisternStatus;
  onRefresh: () => Promise<void>;
};

export function SetupCalibration({ status, onRefresh }: Props) {
  const [form, setForm] = useState<CisternSettings>(status.settings);
  const [showCalibrationModal, setShowCalibrationModal] = useState(false);
  const [manualDistance, setManualDistance] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(status.settings);
  }, [status.settings]);

  const updateField = <K extends keyof CisternSettings>(key: K, value: CisternSettings[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await saveSettings(form);
      setForm(result.settings);
      setMessage(result.interval_cmd_result ? `Saved settings. ${result.interval_cmd_result}` : "Saved settings.");
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setForm(status.settings);
    setMessage("Reset form to current saved settings.");
  };

  const runCalibration = async (url: string, body?: Record<string, unknown>) => {
    try {
      const result = await postAction<{ result?: string; baseline_result?: string }>(url, body);
      setMessage(result.result ?? result.baseline_result ?? "Action completed.");
      setShowCalibrationModal(false);
      setManualDistance("");
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Calibration action failed.");
    }
  };

  const handleCaptureLive = async () => {
    try {
      const result = await postAction<{ ok: boolean; status: CisternStatus }>("/api/capture_live");
      setMessage(result.status.last_ts ? `Live reading captured from ${result.status.last_ts}.` : "No live reading available.");
      await onRefresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not capture live reading.");
    }
  };

  const handleExport = async () => {
    try {
      const result = await postAction<{ ok: boolean; download_url: string }>("/api/export_logs");
      window.location.assign(result.download_url);
      setMessage("Exporting cistern logs as CSV.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not export logs.");
    }
  };

  const calculatedCapacity = Math.round(
    Math.PI *
      Math.pow((Number(form.tank_diameter_ft) * 12) / 2, 2) *
      (Number(form.tank_height_ft) * 12) /
      277.42,
  );

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mb-6 lg:mb-8">
        <h2 className="text-2xl sm:text-3xl font-semibold text-gray-900 mb-2">Setup & Calibration</h2>
        <p className="text-sm sm:text-base text-gray-600">Save setup values into the existing Flask settings store and trigger real calibration actions</p>
      </div>

      {message ? (
        <div className="mb-4 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          {message}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
        <div className="lg:col-span-2 space-y-4 sm:space-y-6">
          <Card className="p-4 sm:p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Tank Dimensions</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="tankHeight">Tank Height (ft)</Label>
                <Input
                  id="tankHeight"
                  type="number"
                  value={form.tank_height_ft}
                  onChange={(e) => updateField("tank_height_ft", Number(e.target.value))}
                  className="mt-1.5"
                />
              </div>
              <div>
                <Label htmlFor="tankDiameter">Tank Diameter (ft)</Label>
                <Input
                  id="tankDiameter"
                  type="number"
                  value={form.tank_diameter_ft}
                  onChange={(e) => updateField("tank_diameter_ft", Number(e.target.value))}
                  className="mt-1.5"
                />
              </div>
              <div className="md:col-span-2">
                <Label htmlFor="tankCapacity">Total Capacity (imperial gallons)</Label>
                <Input
                  id="tankCapacity"
                  type="number"
                  value={form.tank_full_gal}
                  onChange={(e) => updateField("tank_full_gal", Number(e.target.value))}
                  className="mt-1.5"
                />
                <p className="text-sm text-gray-500 mt-1">
                  Geometry check: approximately {calculatedCapacity.toLocaleString()} imperial gallons from height and diameter
                </p>
              </div>
            </div>
          </Card>

          <Card className="p-4 sm:p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Live Measurement Settings</h3>
            <div className="space-y-6">
              <div>
                <Label>Measurement Smoothing (samples)</Label>
                <div className="flex items-center gap-4 mt-2">
                  <Slider
                    value={[form.measurement_smoothing]}
                    onValueChange={(value) => updateField("measurement_smoothing", value[0] ?? form.measurement_smoothing)}
                    min={1}
                    max={50}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm font-medium text-gray-900 w-12">{form.measurement_smoothing}</span>
                </div>
              </div>

              <div>
                <Label>Fill Detection Threshold (imperial gal/hr)</Label>
                <div className="flex items-center gap-4 mt-2">
                  <Slider
                    value={[form.fill_threshold_gal_hr]}
                    onValueChange={(value) => updateField("fill_threshold_gal_hr", value[0] ?? form.fill_threshold_gal_hr)}
                    min={1}
                    max={250}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm font-medium text-gray-900 w-16">{Math.round(form.fill_threshold_gal_hr)}</span>
                </div>
              </div>

              <div>
                <Label>Low Level Alert Threshold (%)</Label>
                <div className="flex items-center gap-4 mt-2">
                  <Slider
                    value={[form.low_alert_pct]}
                    onValueChange={(value) => updateField("low_alert_pct", value[0] ?? form.low_alert_pct)}
                    min={1}
                    max={90}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm font-medium text-gray-900 w-16">{Math.round(form.low_alert_pct)}%</span>
                </div>
              </div>

              <div>
                <Label>Data Timeout (minutes)</Label>
                <div className="flex items-center gap-4 mt-2">
                  <Slider
                    value={[form.data_timeout_minutes]}
                    onValueChange={(value) => updateField("data_timeout_minutes", value[0] ?? form.data_timeout_minutes)}
                    min={1}
                    max={180}
                    step={1}
                    className="flex-1"
                  />
                  <span className="text-sm font-medium text-gray-900 w-16">{form.data_timeout_minutes} min</span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label htmlFor="interval">Measurement Interval (minutes)</Label>
                  <Input
                    id="interval"
                    type="number"
                    value={form.measurement_interval_minutes}
                    onChange={(e) => updateField("measurement_interval_minutes", Number(e.target.value))}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="offset">Sensor Offset (inches)</Label>
                  <Input
                    id="offset"
                    type="number"
                    value={form.sensor_offset_in}
                    onChange={(e) => updateField("sensor_offset_in", Number(e.target.value))}
                    className="mt-1.5"
                  />
                </div>
                <div>
                  <Label htmlFor="haulTank">Haul Tank (imperial gallons)</Label>
                  <Input
                    id="haulTank"
                    type="number"
                    value={form.haul_tank_gal}
                    onChange={(e) => updateField("haul_tank_gal", Number(e.target.value))}
                    className="mt-1.5"
                  />
                </div>
              </div>
            </div>
          </Card>

          <div className="flex gap-3">
            <Button onClick={() => void handleSave()} className="bg-blue-600 hover:bg-blue-700" disabled={saving}>
              <Save className="w-4 h-4 mr-2" />
              {saving ? "Saving..." : "Save Settings"}
            </Button>
            <Button onClick={handleReset} variant="outline">
              <RotateCcw className="w-4 h-4 mr-2" />
              Reset Form
            </Button>
          </div>
        </div>

        <div className="space-y-6">
          <Card className="p-6">
            <h3 className="font-semibold text-gray-900 mb-4 uppercase tracking-wide text-sm">Measurement Status</h3>
            <div className="space-y-4 text-sm">
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Measurement Active</span>
                <span className="font-medium text-gray-900">
                  {status.last_reading_age_seconds != null && status.last_reading_age_seconds < (status.settings.data_timeout_minutes * 60) ? "Yes" : "No"}
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
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Latest ADC</span>
                <span className="font-medium text-gray-900">{status.adc ?? "No data"}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span className="text-gray-600">Current Gallons</span>
                <span className="font-medium text-gray-900">
                  {status.volume_imp_gal != null ? `${Math.round(status.volume_imp_gal)} imp gal` : "No data"}
                </span>
              </div>
            </div>
          </Card>

          <Card className="p-6">
            <h3 className="font-semibold text-gray-900 mb-4">Quick Actions</h3>
            <div className="space-y-2">
              <Button variant="outline" className="w-full justify-start" onClick={() => setShowCalibrationModal(true)}>
                <Wrench className="w-4 h-4 mr-2" />
                Re-Calibrate
              </Button>
              <Button variant="outline" className="w-full justify-start" onClick={() => void runCalibration("/api/calibration/clear")}>
                <Trash2 className="w-4 h-4 mr-2" />
                Clear Calibration
              </Button>
              <Button variant="outline" className="w-full justify-start" onClick={() => void handleCaptureLive()}>
                <Eye className="w-4 h-4 mr-2" />
                Capture Live Reading
              </Button>
              <Button variant="outline" className="w-full justify-start" onClick={() => void handleExport()}>
                <Download className="w-4 h-4 mr-2" />
                Export System Log
              </Button>
            </div>
          </Card>

          <Card className="p-6 bg-blue-50 border-blue-200">
            <div className="text-sm text-blue-900 mb-2 font-medium">Calibration Tip</div>
            <div className="text-sm text-blue-800">
              Use `Calibrate Empty` or `Calibrate Full` for true sensor points. Use manual distance from the top to save a baseline if you know the current water level.
            </div>
          </Card>
        </div>
      </div>

      {showCalibrationModal ? (
        <div className="fixed inset-0 bg-gray-500/75 flex items-center justify-center p-4">
          <div className="bg-white p-6 rounded-lg shadow-lg w-full max-w-md">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900">Re-Calibrate</h3>
              <Button variant="outline" className="p-1" onClick={() => setShowCalibrationModal(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="space-y-4">
              <Button variant="outline" className="w-full justify-start" onClick={() => void runCalibration("/api/calibration/empty")}>
                Calibrate at Empty Level
              </Button>
              <Button variant="outline" className="w-full justify-start" onClick={() => void runCalibration("/api/calibration/full")}>
                Calibrate at Full Level
              </Button>
              <div>
                <Label htmlFor="manualDistance">Manual Distance From Top (inches)</Label>
                <div className="mt-2 flex items-center gap-2">
                  <Input
                    id="manualDistance"
                    type="number"
                    value={manualDistance}
                    onChange={(e) => setManualDistance(e.target.value)}
                  />
                  <Button
                    variant="outline"
                    onClick={() => void runCalibration("/api/calibration/manual", { down_inches: Number(manualDistance || 0) })}
                  >
                    Save Baseline
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
