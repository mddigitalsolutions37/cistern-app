import csv
import io
import os
import uuid
import threading, time, sqlite3
from datetime import datetime, date, timedelta
from flask import Flask, render_template_string, jsonify, request, send_from_directory, Response
import serial
import math

def env_flag(name, default="0"):
    v = os.environ.get(name, default)
    return str(v).strip().lower() in ("1", "true", "yes", "on")

# Local development can keep using the Nano bridge over COM4.
# Cloud deployments should set ENABLE_SERIAL_WORKER=0 and use /api/device/update instead.
SERIAL_PORT = os.environ.get("SERIAL_PORT", "COM4")
SERIAL_BAUD = int(os.environ.get("SERIAL_BAUD", "115200"))
DB_PATH = os.environ.get("DB_PATH", "cistern.db")
ENABLE_SERIAL_WORKER = env_flag("ENABLE_SERIAL_WORKER", "1")
UI2_BUILD_DIR = os.path.join(os.path.dirname(__file__), "Cistern_UI", "src", "build")

# ---------------- DB ----------------
def db_init():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            lvl_pct REAL,
            gal_imp REAL,
            adc INTEGER,
            cal INTEGER,
            packet TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # Level 3 tables
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fill_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,           -- 'TRUCK_FULL', 'HAUL_TRIP', 'MANUAL_SET'
            gallons_added REAL,           -- + gallons added (can be NULL)
            note TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_daily (
            day TEXT PRIMARY KEY,         -- 'YYYY-MM-DD'
            gal_used REAL NOT NULL,
            samples INTEGER NOT NULL,
            updated_ts TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()

def db_insert(ts, lvl_pct, gal_imp, adc, cal, packet):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO readings (ts, lvl_pct, gal_imp, adc, cal, packet) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, lvl_pct, gal_imp, adc, cal, packet),
    )
    con.commit()
    con.close()

def db_recent(n=25):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT ts, lvl_pct, gal_imp, adc, cal, packet FROM readings ORDER BY id DESC LIMIT ?", (n,))
    rows = cur.fetchall()
    con.close()
    return rows

def setting_get(key, default=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    if not row:
        return default
    return row[0]

def setting_set(key, value):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value))
    )
    con.commit()
    con.close()

def load_settings():
    # Level 2 defaults
    tank_height_ft = float(setting_get("tank_height_ft", "9.5"))
    tank_diameter_ft = float(setting_get("tank_diameter_ft", "8"))
    tank_full_gal  = float(setting_get("tank_full_gal",  "2974"))
    baseline_pct   = float(setting_get("baseline_pct",   "51.8"))
    baseline_ts    = setting_get("baseline_ts", None)
    measurement_smoothing = int(float(setting_get("measurement_smoothing", "20")))
    fill_threshold_gal_hr = float(setting_get("fill_threshold_gal_hr", "10"))
    data_timeout_minutes = int(float(setting_get("data_timeout_minutes", "30")))
    measurement_interval_minutes = int(float(setting_get("measurement_interval_minutes", "1")))
    sensor_offset_in = float(setting_get("sensor_offset_in", "0"))

    # Level 3 defaults
    haul_tank_gal  = float(setting_get("haul_tank_gal",  "600"))
    low_alert_pct  = float(setting_get("low_alert_pct",  "30"))
    target_pct     = float(setting_get("target_pct",     "80"))

    # Baseline override (0=auto, 1=force baseline)
    force_baseline = int(float(setting_get("force_baseline", "0")))

    # NEW: used by Option A auto-finalize
    usage_last_finalized_day = setting_get("usage_last_finalized_day", None)

    return {
        "tank_height_ft": tank_height_ft,
        "tank_diameter_ft": tank_diameter_ft,
        "tank_full_gal": tank_full_gal,
        "baseline_pct": baseline_pct,
        "baseline_ts": baseline_ts,
        "measurement_smoothing": measurement_smoothing,
        "fill_threshold_gal_hr": fill_threshold_gal_hr,
        "data_timeout_minutes": data_timeout_minutes,
        "measurement_interval_minutes": measurement_interval_minutes,
        "sensor_offset_in": sensor_offset_in,
        "haul_tank_gal": haul_tank_gal,
        "low_alert_pct": low_alert_pct,
        "target_pct": target_pct,
        "force_baseline": force_baseline,
        "usage_last_finalized_day": usage_last_finalized_day
    }

# -------- Level 3 DB helpers --------
def today_str():
    return datetime.now().date().isoformat()

def db_get_day_samples(day_iso, limit=2000):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT ts, lvl_pct, gal_imp, cal
        FROM readings
        WHERE ts >= ? AND ts < ?
        ORDER BY ts ASC
        LIMIT ?
    """, (day_iso + "T00:00:00", (day_iso + "T23:59:59"), int(limit)))
    rows = cur.fetchall()
    con.close()
    return rows

def db_get_last_reading():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT ts, gal_imp, lvl_pct, cal FROM readings ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    con.close()
    return row

def db_upsert_usage_day(day, gal_used, samples):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO usage_daily(day, gal_used, samples, updated_ts)
        VALUES(?,?,?,?)
        ON CONFLICT(day) DO UPDATE SET
            gal_used=excluded.gal_used,
            samples=excluded.samples,
            updated_ts=excluded.updated_ts
    """, (day, float(gal_used), int(samples), datetime.now().isoformat(timespec="seconds")))
    con.commit()
    con.close()

def db_usage_recent(days=30):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT day, gal_used, samples
        FROM usage_daily
        ORDER BY day DESC
        LIMIT ?
    """, (int(days),))
    rows = cur.fetchall()
    con.close()
    return rows

def db_level_history(days=30):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cutoff = (datetime.now() - timedelta(days=int(days))).isoformat(timespec="seconds")
    cur.execute("""
        SELECT substr(ts, 1, 10) AS day,
               MAX(ts) AS ts,
               AVG(lvl_pct) AS lvl_pct,
               AVG(gal_imp) AS gal_imp
        FROM readings
        WHERE ts >= ?
        GROUP BY substr(ts, 1, 10)
        ORDER BY day ASC
    """, (cutoff,))
    rows = cur.fetchall()
    con.close()
    return rows

def db_add_fill_event(kind, gallons_added=None, note=None):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO fill_events(ts, kind, gallons_added, note)
        VALUES(?,?,?,?)
    """, (datetime.now().isoformat(timespec="seconds"), kind, gallons_added, note))
    con.commit()
    con.close()

def db_fill_events_recent(n=20):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT ts, kind, gallons_added, note
        FROM fill_events
        ORDER BY id DESC
        LIMIT ?
    """, (int(n),))
    rows = cur.fetchall()
    con.close()
    return rows

def baseline_age_days(settings):
    baseline_ts = settings.get("baseline_ts")
    if not baseline_ts:
        return None
    try:
        return max(0, (datetime.now() - datetime.fromisoformat(baseline_ts)).days)
    except Exception:
        return None

def current_status_payload():
    settings = load_settings()
    live = dict(latest)
    if not live.get("last_ts"):
        db_last = db_get_last_reading()
        if db_last:
            db_ts, db_gal, db_lvl, db_cal = db_last
            live["last_ts"] = db_ts
            live["gal_imp"] = db_gal
            live["lvl_pct"] = db_lvl
            live["cal"] = db_cal
            live["packet"] = live.get("packet") or "DB_FALLBACK"

    last_ts = live.get("last_ts")
    age = None
    if last_ts:
        try:
            age = int((datetime.now() - datetime.fromisoformat(last_ts)).total_seconds())
        except Exception:
            age = None

    avg_daily = usage_avg_daily(30)
    tank_full = float(settings.get("tank_full_gal", 2974))
    baseline_pct = float(settings.get("baseline_pct", 0))
    baseline_gal = gal_from_pct(tank_full, baseline_pct)
    forced = int(settings.get("force_baseline", 0)) == 1

    cal_valid = (live.get("cal") or 0) >= 1 and live.get("lvl_pct") is not None
    if forced:
        display_mode = "BASELINE_FORCED"
        level_percent = baseline_pct
        volume_imp_gal = baseline_gal
    elif cal_valid:
        display_mode = "CALIBRATED"
        level_percent = live.get("lvl_pct")
        volume_imp_gal = live.get("gal_imp")
    else:
        display_mode = "BASELINE"
        level_percent = baseline_pct
        volume_imp_gal = baseline_gal

    days_to_empty = None
    if avg_daily and avg_daily > 0 and volume_imp_gal is not None:
        days_to_empty = float(volume_imp_gal) / float(avg_daily)

    alerts = []
    timeout_seconds = max(60, int(settings.get("data_timeout_minutes", 30)) * 60)
    low_alert_pct = float(settings.get("low_alert_pct", 30))
    fill_threshold = float(settings.get("fill_threshold_gal_hr", 10))
    baseline_days = baseline_age_days(settings)

    if age is None:
        alerts.append({"severity": "error", "code": "NO_DATA", "message": "No live readings received yet."})
    elif age > timeout_seconds:
        alerts.append({"severity": "error", "code": "STALE_DATA", "message": f"Last reading is {age} seconds old."})

    if level_percent is not None and float(level_percent) <= low_alert_pct:
        alerts.append({
            "severity": "warning",
            "code": "LOW_LEVEL",
            "message": f"Water level is below the {low_alert_pct:.0f}% threshold.",
        })

    if baseline_days is not None and baseline_days >= 90:
        alerts.append({
            "severity": "info",
            "code": "BASELINE_OLD",
            "message": f"Baseline is {baseline_days} days old.",
        })

    if forced:
        alerts.append({
            "severity": "info",
            "code": "BASELINE_FORCED",
            "message": "Baseline override is enabled, so live calibrated gallons are not being displayed.",
        })

    packet = live.get("packet") or ""
    if packet.startswith("SERIAL_ERROR:"):
        alerts.append({"severity": "error", "code": "SERIAL_ERROR", "message": packet})

    return {
        **live,
        "age_seconds": age,
        "last_reading_age_seconds": age,
        "level_percent": level_percent,
        "volume_imp_gal": volume_imp_gal,
        "avg_daily_use_imp_gal": avg_daily,
        "days_to_empty": days_to_empty,
        "baseline_age_days": baseline_days,
        "display_mode": display_mode,
        "fill_detection_threshold_imp_gal_per_hour": fill_threshold,
        "alerts": alerts,
        "bridge_online": bridge_is_online(),
        "bridge_device_id": bridge_state.get("device_id"),
        "bridge_last_seen_ts": bridge_state.get("last_seen_ts"),
        "settings": settings,
    }

# ---------------- Packet Parse ----------------
def parse_packet(line: str):
    if not line.startswith("LVL:"):
        return None
    parts = line.split(";")
    out = {"packet": line, "lvl_pct": None, "gal_imp": None, "adc": None, "cal": None}
    for p in parts:
        if ":" not in p:
            continue
        k, v = p.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k == "LVL":
            out["lvl_pct"] = None if v == "NA" else float(v)
        elif k == "G":
            out["gal_imp"] = None if v == "NA" else float(v)
        elif k == "ADC":
            out["adc"] = int(v)
        elif k == "CAL":
            out["cal"] = int(v)
    return out

def _coerce_optional_float(value, field_name):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a number or null")
    try:
        return float(value)
    except Exception:
        raise ValueError(f"{field_name} must be a number or null")

def _coerce_optional_int(value, field_name):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer or null")
    try:
        return int(value)
    except Exception:
        raise ValueError(f"{field_name} must be an integer or null")

def _coerce_cal_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return 1 if int(value) else 0
    except Exception:
        raise ValueError("calibrated/cal must be a bool, int, or null")

latest = {"last_ts": None, "lvl_pct": None, "gal_imp": None, "adc": None, "cal": None, "packet": None}
cmd_state = {"last_cmd": None, "last_result": None, "last_result_ts": None, "transport": None}
bridge_state = {"last_seen_ts": None, "device_id": None, "last_command_ts": None}
cmd_queue = []
cmd_lock = threading.Lock()
BRIDGE_DEVICE_ID = "cistern_001"
BRIDGE_ONLINE_TIMEOUT_SEC = 45

# ---------------- Serial Manager ----------------
ser = None
ser_lock = threading.Lock()

def open_serial():
    global ser
    if ser and ser.is_open:
        return ser
    ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
    return ser

def safe_write(cmd: str) -> str:
    global cmd_state
    cmd = (cmd or "").strip()
    if not cmd:
        return "No command"
    with ser_lock:
        try:
            s = open_serial()
            s.write((cmd + "\n").encode("utf-8", errors="ignore"))
            cmd_state["last_cmd"] = cmd
            cmd_state["last_result"] = "Sent"
            cmd_state["last_result_ts"] = datetime.now().isoformat(timespec="seconds")
            return f"Sent: {cmd}"
        except Exception as e:
            cmd_state["last_cmd"] = cmd
            cmd_state["last_result"] = f"SERIAL_ERROR: {e}"
            cmd_state["last_result_ts"] = datetime.now().isoformat(timespec="seconds")
            return f"SERIAL_ERROR: {e}"

def bridge_is_online(now_dt=None):
    if now_dt is None:
        now_dt = datetime.now()
    last_seen_ts = bridge_state.get("last_seen_ts")
    if not last_seen_ts:
        return False
    try:
        age = (now_dt - datetime.fromisoformat(last_seen_ts)).total_seconds()
        return age <= BRIDGE_ONLINE_TIMEOUT_SEC
    except Exception:
        return False

def mark_bridge_seen(device_id=None):
    bridge_state["last_seen_ts"] = datetime.now().isoformat(timespec="seconds")
    if device_id:
        bridge_state["device_id"] = device_id

def queue_bridge_command(cmd: str, device_id=BRIDGE_DEVICE_ID) -> str:
    global cmd_state
    cmd = (cmd or "").strip()
    if not cmd:
        return "No command"

    queued_ts = datetime.now().isoformat(timespec="seconds")
    item = {
        "id": uuid.uuid4().hex,
        "device_id": device_id,
        "cmd": cmd,
        "created_ts": queued_ts,
        "status": "queued",
        "result": None,
        "result_ts": None,
        "dispatch_ts": None,
    }
    with cmd_lock:
        cmd_queue.append(item)

    cmd_state["last_cmd"] = cmd
    cmd_state["last_result"] = f"Queued for Wi-Fi bridge: {cmd}"
    cmd_state["last_result_ts"] = queued_ts
    cmd_state["transport"] = "wifi_bridge"
    return f"Queued: {cmd}"

def send_command(cmd: str) -> str:
    # Prefer the ESP32 Wi-Fi bridge when it is online so the same Flask UI
    # can reach the remote HC-12 path over the internet. Fall back to serial
    # for local bench testing if the bridge is offline.
    if bridge_is_online():
        return queue_bridge_command(cmd)

    result = safe_write(cmd)
    cmd_state["transport"] = "serial"
    return result

# ---------------- Baseline math ----------------
def pct_from_down_from_top(tank_height_ft: float, down_ft: int, down_in: int) -> float:
    down = float(down_ft) + (float(down_in) / 12.0)
    depth = tank_height_ft - down
    if tank_height_ft <= 0:
        return 0.0
    pct = (depth / tank_height_ft) * 100.0
    return max(0.0, min(100.0, pct))

def gal_from_pct(tank_full_gal: float, pct: float) -> float:
    return (pct / 100.0) * tank_full_gal

# ---------------- Level 3: Effective gallons + usage ----------------
def gal_effective(lvl_pct, gal_imp, cal, settings):
    # manual override to force baseline even if CAL=1
    try:
        force_baseline = int(settings.get("force_baseline", 0))
    except Exception:
        force_baseline = 0

    tank_full = float(settings.get("tank_full_gal", 2974))
    baseline_pct = float(settings.get("baseline_pct", 0))
    baseline_gal = (baseline_pct / 100.0) * tank_full

    if force_baseline == 1:
        return baseline_gal

    try:
        cal_ok = (int(cal) >= 1)   # accept CAL:1 (true) and CAL:2 (baseline EEPROM)
    except Exception:
        cal_ok = False

    if cal_ok and gal_imp is not None:
        return float(gal_imp)

    return baseline_gal

def compute_usage_for_day(day_iso):
    """
    Daily usage (robust):
    - Use the first sample and last sample of the day (effective gallons)
    - Usage = max(0, start - end)
    This ignores all the minute-to-minute bouncing noise.
    """
    settings = load_settings()
    rows = db_get_day_samples(day_iso)
    if len(rows) < 2:
        return None

    # rows are: (ts, lvl_pct, gal_imp, cal)
    ts0, lvl0, gal0, cal0 = rows[0]
    ts1, lvl1, gal1, cal1 = rows[-1]

    g_start = gal_effective(lvl0, gal0, cal0 or 0, settings)
    g_end   = gal_effective(lvl1, gal1, cal1 or 0, settings)

    used = max(0.0, g_start - g_end)
    return used, len(rows)

def usage_avg_daily(days=30):
    rows = db_usage_recent(days)
    vals = [float(r[1]) for r in rows if r[1] is not None and float(r[1]) >= 0]
    if not vals:
        return None
    return sum(vals) / len(vals)

# ---------------- Option A: auto finalize yesterday once/day ----------------
def auto_finalize_yesterday_once_per_day(now_dt=None):
    """
    On the first packet of a new day:
    - finalize yesterday
    - mark 'usage_last_finalized_day' = today (meaning: done the finalize for this day)
    """
    if now_dt is None:
        now_dt = datetime.now()

    today = now_dt.date().isoformat()
    last_done = setting_get("usage_last_finalized_day", None)

    # Already did the daily finalize for *today*? then do nothing.
    if last_done == today:
        return

    yesterday = (now_dt.date() - timedelta(days=1)).isoformat()

    res = compute_usage_for_day(yesterday)
    if not res:
        # Not enough data; don't mark as done so it can try again next packet
        return

    used, samples = res
    db_upsert_usage_day(yesterday, used, samples)

    # Mark that we successfully finalized yesterday for today's rollover
    setting_set("usage_last_finalized_day", today)

def serial_worker():
    global latest, ser
    while True:
        try:
            with ser_lock:
                s = open_serial()
            time.sleep(0.2)

            while True:
                with ser_lock:
                    line = s.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                parsed = parse_packet(line)
                ts = datetime.now().isoformat(timespec="seconds")

                if parsed:
                    latest = {"last_ts": ts, **parsed}
                    db_insert(ts, parsed["lvl_pct"], parsed["gal_imp"], parsed["adc"], parsed["cal"], parsed["packet"])

                    # NEW: Option A auto-finalize yesterday (once/day) after we receive a valid sample
                    auto_finalize_yesterday_once_per_day(datetime.now())

                else:
                    latest["last_ts"] = ts
                    latest["packet"] = line

        except Exception as e:
            latest["packet"] = f"SERIAL_ERROR: {e}"
            try:
                if ser:
                    ser.close()
            except Exception:
                pass
            ser = None
            time.sleep(2.0)

# ---------------- Flask ----------------
app = Flask(__name__)

PAGE = """<!doctype html><html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Cistern Monitor Rev1</title>
<style>
body{font-family:Arial;margin:18px}
.row{display:flex;gap:14px;flex-wrap:wrap}
.card{border:1px solid #ddd;border-radius:10px;padding:14px;min-width:260px;flex:1}
.big{font-size:28px;font-weight:700}
.muted{color:#666}
.ok{color:#0a0;font-weight:700}
.bad{color:#a00;font-weight:700}
table{border-collapse:collapse;width:100%;margin-top:16px}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;font-size:14px}
code{background:#f6f6f6;padding:2px 6px;border-radius:6px;word-break:break-word}
.btn{padding:10px 14px;border:1px solid #ccc;border-radius:10px;background:#fff;cursor:pointer}
.btn:hover{background:#f7f7f7}
.cmdrow{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:10px}
input[type=text], input[type=number], select{padding:10px;border-radius:10px;border:1px solid #ccc;min-width:160px}
.small{font-size:13px}
hr{border:none;border-top:1px solid #eee;margin:14px 0}
</style></head><body>
<h2>Cistern Monitor (Rev1)</h2>

<div class="row">
  <div class="card">
    <div class="muted">Status</div>
    <div id="status" class="big">—</div>
    <div class="muted">Last heard: <span id="last_ts">—</span></div>
    <div class="muted">Calibration valid: <span id="cal">—</span></div>
    <div class="muted small">Display mode: <span id="mode">—</span></div>

    <div class="cmdrow" style="margin-top:12px;">
      <button class="btn" onclick="toggleBaseline()">
        Baseline Override: <b id="baselineToggle">—</b>
      </button>
      <span class="muted small">(AUTO uses CAL when valid)</span>
    </div>
  </div>

  <div class="card">
    <div class="muted">Percent Full</div>
    <div id="lvl" class="big">—</div>
    <div class="muted">Gallons remaining: <span id="gal">—</span></div>
  </div>

  <div class="card">
    <div class="muted">ADC</div>
    <div id="adc" class="big">—</div>
    <div class="muted">Packet: <code id="pkt">—</code></div>
  </div>
</div>

<div class="card" style="margin-top:14px; max-width:980px;">
  <div class="muted">Controls</div>
  <div class="cmdrow">
    <button class="btn" onclick="sendCmd('CAL_EMPTY')">Calibrate EMPTY</button>
    <button class="btn" onclick="sendCmd('CAL_FULL')">Calibrate FULL</button>
    <button class="btn" onclick="sendCmd('GET_CAL')">Get Cal</button>
  </div>

  <div class="cmdrow">
    <input id="customCmd" type="text" placeholder="Type command (e.g., PING, SET_CAP 2974)"/>
    <button class="btn" onclick="sendCustom()">Send</button>
  </div>

  <div class="muted" style="margin-top:10px;">
    Last command result: <code id="cmdResult">—</code>
  </div>

  <hr/>

  <div class="muted">Baseline Setup (Save Baseline also pushes to PCB)</div>
  <div class="cmdrow">
    <label class="small">Tank height (ft):</label>
    <input id="tankHeight" type="number" step="0.01"/>
    <label class="small">Tank full (imp gal):</label>
    <input id="tankFull" type="number" step="1"/>
  </div>

  <div class="cmdrow">
    <label class="small">Water is</label>
    <input id="downFt" type="number" step="1" style="min-width:90px"/> <span class="small">ft</span>
    <input id="downIn" type="number" step="1" style="min-width:90px"/> <span class="small">in</span>
    <span class="small">down from top</span>
    <button class="btn" onclick="calcBaseline()">Calculate</button>
    <button class="btn" onclick="saveBaseline()">Save Baseline</button>
  </div>

  <div class="muted small" style="margin-top:8px;">
    Baseline result: <code id="baselineResult">—</code>
  </div>

  <hr/>

  <div class="muted">Level 3 (Usage + Hauling)</div>
  <div class="cmdrow">
    <button class="btn" onclick="recomputeToday()">Recompute Today's Usage</button>
    <div class="muted small">Avg daily usage: <b id="avgDaily">—</b></div>
    <div class="muted small">Days to empty: <b id="daysEmpty">—</b></div>
    <div class="muted small">Days to low: <b id="daysLow">—</b></div>
  </div>

  <div class="cmdrow">
    <label class="small">Haul tank (imp gal):</label>
    <input id="haulTank" type="number" step="1" style="min-width:140px"/>
    <label class="small">Low alert (%):</label>
    <input id="lowPct" type="number" step="1" style="min-width:120px"/>
    <label class="small">Target (%):</label>
    <input id="targetPct" type="number" step="1" style="min-width:120px"/>
    <button class="btn" onclick="saveHaulSettings()">Save</button>
    <button class="btn" onclick="refreshHaulPlan()">Refresh Plan</button>
  </div>

  <div class="muted small" style="margin-top:8px;">
    Hauling plan:
    <code id="haulMsg">—</code>
  </div>

  <table>
    <thead><tr><th>Date</th><th>Trip</th><th>Gallons</th></tr></thead>
    <tbody id="haulRows"></tbody>
  </table>

  <hr/>

  <div class="muted">Fill / Haul Log</div>
  <div class="cmdrow">
    <select id="fillKind">
      <option value="HAUL_TRIP">HAUL_TRIP</option>
      <option value="TRUCK_FULL">TRUCK_FULL</option>
      <option value="MANUAL_SET">MANUAL_SET</option>
    </select>
    <input id="fillGal" type="number" step="1" placeholder="Gallons added (optional)" style="min-width:220px"/>
    <input id="fillNote" type="text" placeholder="Note (optional)" style="min-width:260px"/>
    <button class="btn" onclick="logFill()">Log</button>
  </div>

  <table>
    <thead><tr><th>Time</th><th>Type</th><th>Gal</th><th>Note</th></tr></thead>
    <tbody id="fillRows"></tbody>
  </table>
</div>

<h3>Recent Readings</h3>
<table>
<thead><tr><th>Time</th><th>%</th><th>Imp Gal</th><th>ADC</th><th>CAL</th><th>Packet</th></tr></thead>
<tbody id="rows"></tbody>
</table>

<script>
let settings = null;
let baselinePreview = null;

async function sendCmd(cmd){
  const r = await fetch("/api/send_cmd", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({cmd})
  });
  const j = await r.json();
  document.getElementById("cmdResult").textContent = j.result ?? "—";
}

function sendCustom(){
  const v = document.getElementById("customCmd").value.trim();
  if(!v) return;
  sendCmd(v);
  document.getElementById("customCmd").value="";
}

async function toggleBaseline(){
  const enable = (settings?.force_baseline === 1) ? 0 : 1;
  await fetch("/api/baseline/toggle", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({enable})
  });
  await loadSettings();
  await refresh();
}

async function loadSettings(){
  settings = await fetch("/api/settings").then(r=>r.json());
  document.getElementById("tankHeight").value = settings.tank_height_ft ?? 9.5;
  document.getElementById("tankFull").value = settings.tank_full_gal ?? 2974;

  document.getElementById("haulTank").value = settings.haul_tank_gal ?? 600;
  document.getElementById("lowPct").value = settings.low_alert_pct ?? 30;
  document.getElementById("targetPct").value = settings.target_pct ?? 80;

  document.getElementById("baselineResult").textContent =
    `Saved baseline: ${Number(settings.baseline_pct).toFixed(1)}% (saved ${settings.baseline_ts ?? "—"})`;

  document.getElementById("baselineToggle").textContent =
    (settings.force_baseline === 1) ? "ON" : "AUTO";
}

function calcBaseline(){
  const h = Number(document.getElementById("tankHeight").value || 9.5);
  const full = Number(document.getElementById("tankFull").value || 2974);
  const ft = Number(document.getElementById("downFt").value || 0);
  const inch = Number(document.getElementById("downIn").value || 0);

  const down = ft + (inch/12.0);
  const depth = h - down;
  let pct = (depth / h) * 100.0;
  pct = Math.max(0, Math.min(100, pct));
  const gal = (pct/100.0) * full;

  baselinePreview = {tank_height_ft:h, tank_full_gal:full, baseline_pct:pct};
  document.getElementById("baselineResult").textContent =
    `Preview: down ${ft}' ${inch}" => ${pct.toFixed(1)}% (~${Math.round(gal)} imp gal)`;
}

async function saveBaseline(){
  // compute baseline pct from fields (same as calcBaseline)
  const tankHeight = Number(document.getElementById("tankHeight").value || 9.5);
  const tankFull   = Number(document.getElementById("tankFull").value || 2974);
  const ft         = Number(document.getElementById("downFt").value || 0);
  const inch       = Number(document.getElementById("downIn").value || 0);

  const down = ft + (inch/12.0);
  const depth = tankHeight - down;
  let pct = (depth / tankHeight) * 100.0;
  pct = Math.max(0, Math.min(100, pct));

  const payload = {
    tank_height_ft: tankHeight,
    tank_full_gal: tankFull,
    down_ft: ft,
    down_in: inch
  };

  const r = await fetch("/api/baseline_set", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  const j = await r.json();

  document.getElementById("baselineResult").textContent =
    `Saved baseline: ${Number(j.baseline_pct).toFixed(1)}% (saved ${j.baseline_ts})`;

  // push baseline to PCB: CLR_CAL then SET_BASELINE <pct>
  await fetch("/api/send_cmd", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ cmd: "CLR_CAL" })
  });

  await new Promise(res => setTimeout(res, 300));

  await fetch("/api/send_cmd", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ cmd: `SET_BASELINE ${pct.toFixed(1)}` })
  });

  await loadSettings();
}

async function recomputeToday(){
  await fetch("/api/usage/recompute_today", {method:"POST"});
  await refreshUsage();
}

async function refreshUsage(){
  const u = await fetch("/api/usage/summary").then(r=>r.json());
  const avg = u.avg_daily;
  const dte = u.days_to_empty;
  document.getElementById("avgDaily").textContent = (avg!=null) ? (avg.toFixed(1)+" gal/day") : "—";
  document.getElementById("daysEmpty").textContent = (dte!=null) ? (dte.toFixed(1)+" days") : "—";
  await refreshHaulPlan();
}

async function saveHaulSettings(){
  const payload = {
    haul_tank_gal: Number(document.getElementById("haulTank").value || 600),
    low_alert_pct: Number(document.getElementById("lowPct").value || 30),
    target_pct: Number(document.getElementById("targetPct").value || 80),
  };
  await fetch("/api/haul/settings_set", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  });
  await loadSettings();
  await refreshHaulPlan();
}

async function refreshHaulPlan(){
  const j = await fetch("/api/haul/plan").then(r=>r.json());
  const tbody=document.getElementById("haulRows"); tbody.innerHTML="";
  document.getElementById("haulMsg").textContent = j.msg ?? "OK";

  const daysLow = j.days_to_low;
  document.getElementById("daysLow").textContent = (daysLow!=null) ? (daysLow.toFixed(1)+" days") : "—";

  const plan = j.plan || [];
  for(const p of plan){
    const tr=document.createElement("tr");
    tr.innerHTML = `<td>${p.date}</td><td>${p.trip_number}</td><td>${Math.round(p.gallons)}</td>`;
    tbody.appendChild(tr);
  }
}

async function logFill(){
  const kind = document.getElementById("fillKind").value;
  const galRaw = document.getElementById("fillGal").value;
  const note = document.getElementById("fillNote").value.trim();
  const gallons_added = galRaw ? Number(galRaw) : null;

  await fetch("/api/fill/log", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({kind, gallons_added, note})
  });

  document.getElementById("fillGal").value="";
  document.getElementById("fillNote").value="";
  await refreshFillEvents();
}

async function refreshFillEvents(){
  const rows = await fetch("/api/fill/recent").then(r=>r.json());
  const tbody=document.getElementById("fillRows"); tbody.innerHTML="";
  for(const r of rows){
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${r.ts}</td><td>${r.kind}</td><td>${r.gallons_added ?? ""}</td><td>${r.note ?? ""}</td>`;
    tbody.appendChild(tr);
  }
}

async function refresh(){
  const s = await fetch("/api/status").then(r=>r.json());
  const age = s.age_seconds;
  let statusText="NO DATA", statusClass="bad";
  if (s.last_ts && age!==null){
    if (age < 120){ statusText="ONLINE"; statusClass="ok"; }
    else { statusText="STALE"; statusClass="bad"; }
  }
  const statusEl=document.getElementById("status");
  statusEl.textContent=statusText; statusEl.className="big "+statusClass;

  document.getElementById("last_ts").textContent=s.last_ts ?? "—";
  document.getElementById("adc").textContent=(s.adc!=null)?s.adc:"—";
  document.getElementById("pkt").textContent=s.packet ?? "—";
  document.getElementById("cal").textContent=(s.cal===1)?"YES":"NO";

  const tankFull = Number(settings?.tank_full_gal ?? 2974);
  const baselinePct = Number(settings?.baseline_pct ?? 0);
  const forced = (settings?.force_baseline === 1);

  let displayMode = "—";
  let pct = null;
  let gal = null;

  const calValid = (s.cal >= 1) && (s.lvl_pct != null);   // accept CAL:1 and CAL:2

  if (forced) {
    displayMode = "BASELINE (FORCED)";
    pct = baselinePct;
    gal = (pct/100.0) * tankFull;
  } else if (calValid) {
    displayMode = "CALIBRATED";
    pct = s.lvl_pct;
    gal = s.gal_imp;
  } else {
    displayMode = "BASELINE";
    pct = baselinePct;
    gal = (pct/100.0) * tankFull;
  }

  document.getElementById("mode").textContent = displayMode;
  document.getElementById("lvl").textContent=(pct!=null)?(Number(pct).toFixed(1)+"%"):"—";
  document.getElementById("gal").textContent=(gal!=null)?(Math.round(gal)+" imp gal"):"—";

  const c = await fetch("/api/cmd_status").then(r=>r.json());
  document.getElementById("cmdResult").textContent = c.last_result ? (c.last_result + (c.last_cmd ? (" ("+c.last_cmd+")") : "")) : "—";

  const rows = await fetch("/api/recent").then(r=>r.json());
  const tbody=document.getElementById("rows"); tbody.innerHTML="";
  for(const r of rows){
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${r.ts}</td><td>${r.lvl_pct ?? ""}</td><td>${r.gal_imp ?? ""}</td><td>${r.adc ?? ""}</td><td>${r.cal ?? ""}</td><td><code>${r.packet}</code></td>`;
    tbody.appendChild(tr);
  }
}

(async ()=>{
  await loadSettings();
  await refresh();
  await refreshUsage();
  await refreshFillEvents();
  setInterval(refresh, 2000);
  setInterval(refreshUsage, 15000);
  setInterval(refreshFillEvents, 15000);
})();
</script></body></html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE)

# -------- Settings APIs --------
@app.route("/api/settings")
def api_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.get_json(silent=True) or {}

    tank_height_ft = max(0.1, float(data.get("tank_height_ft", setting_get("tank_height_ft", "9.5"))))
    tank_diameter_ft = max(0.1, float(data.get("tank_diameter_ft", setting_get("tank_diameter_ft", "8"))))
    tank_full_gal = max(1.0, float(data.get("tank_full_gal", setting_get("tank_full_gal", "2974"))))
    measurement_smoothing = max(1, min(100, int(float(data.get("measurement_smoothing", setting_get("measurement_smoothing", "20"))))))
    fill_threshold_gal_hr = max(0.0, float(data.get("fill_threshold_gal_hr", setting_get("fill_threshold_gal_hr", "10"))))
    low_alert_pct = max(0.0, min(100.0, float(data.get("low_alert_pct", setting_get("low_alert_pct", "30")))))
    data_timeout_minutes = max(1, min(1440, int(float(data.get("data_timeout_minutes", setting_get("data_timeout_minutes", "30"))))))
    measurement_interval_minutes = max(1, min(60, int(float(data.get("measurement_interval_minutes", setting_get("measurement_interval_minutes", "1"))))))
    sensor_offset_in = max(0.0, float(data.get("sensor_offset_in", setting_get("sensor_offset_in", "0"))))
    haul_tank_gal = max(1.0, float(data.get("haul_tank_gal", setting_get("haul_tank_gal", "600"))))
    target_pct = max(0.0, min(100.0, float(data.get("target_pct", setting_get("target_pct", "80")))))

    setting_set("tank_height_ft", tank_height_ft)
    setting_set("tank_diameter_ft", tank_diameter_ft)
    setting_set("tank_full_gal", tank_full_gal)
    setting_set("measurement_smoothing", measurement_smoothing)
    setting_set("fill_threshold_gal_hr", fill_threshold_gal_hr)
    setting_set("low_alert_pct", low_alert_pct)
    setting_set("data_timeout_minutes", data_timeout_minutes)
    setting_set("measurement_interval_minutes", measurement_interval_minutes)
    setting_set("sensor_offset_in", sensor_offset_in)
    setting_set("haul_tank_gal", haul_tank_gal)
    setting_set("target_pct", target_pct)

    interval_cmd_result = None
    interval_ms = measurement_interval_minutes * 60000
    if interval_ms:
        interval_cmd_result = safe_write(f"SET_INT {interval_ms}")

    return jsonify({
        "ok": True,
        "settings": load_settings(),
        "interval_cmd_result": interval_cmd_result,
    })

@app.route("/api/baseline_set", methods=["POST"])
def api_baseline_set():
    data = request.get_json(silent=True) or {}

    tank_height_ft = float(data.get("tank_height_ft", 9.5))
    tank_full_gal  = float(data.get("tank_full_gal", 2974))
    down_ft = int(float(data.get("down_ft", 0)))
    down_in = int(float(data.get("down_in", 0)))

    pct = pct_from_down_from_top(tank_height_ft, down_ft, down_in)

    setting_set("tank_height_ft", tank_height_ft)
    setting_set("tank_full_gal", tank_full_gal)
    setting_set("baseline_pct", pct)
    ts = datetime.now().isoformat(timespec="seconds")
    setting_set("baseline_ts", ts)

    return jsonify({"baseline_pct": pct, "baseline_ts": ts})

@app.route("/api/usage/recompute_day", methods=["POST"])
def api_usage_recompute_day():
    data = request.get_json(silent=True) or {}
    day = (data.get("day") or "").strip()
    if not day:
        return jsonify({"ok": False, "msg": "Missing day"}), 400

    res = compute_usage_for_day(day)
    if not res:
        return jsonify({"ok": False, "msg": "Not enough samples"}), 200

    used, samples = res
    db_upsert_usage_day(day, used, samples)
    return jsonify({"ok": True, "day": day, "gal_used": used, "samples": samples})


@app.route("/api/baseline/toggle", methods=["POST"])
def api_baseline_toggle():
    data = request.get_json(silent=True) or {}
    enable = 1 if bool(data.get("enable", False)) else 0
    setting_set("force_baseline", enable)
    return jsonify({"force_baseline": enable})

@app.route("/api/haul/settings_set", methods=["POST"])
def api_haul_settings_set():
    data = request.get_json(silent=True) or {}
    haul_tank_gal = float(data.get("haul_tank_gal", 600))
    low_alert_pct = float(data.get("low_alert_pct", 30))
    target_pct    = float(data.get("target_pct", 80))

    haul_tank_gal = max(1.0, haul_tank_gal)
    low_alert_pct = max(0.0, min(100.0, low_alert_pct))
    target_pct    = max(0.0, min(100.0, target_pct))

    setting_set("haul_tank_gal", haul_tank_gal)
    setting_set("low_alert_pct", low_alert_pct)
    setting_set("target_pct", target_pct)
    return jsonify({"ok": True})

# -------- Status + readings APIs --------
@app.route("/api/status")
def api_status():
    return jsonify(current_status_payload())

@app.route("/api/recent")
def api_recent():
    out=[]
    for (ts,lvl,gal,adc,cal,pkt) in db_recent(25):
        out.append({"ts":ts,"lvl_pct":lvl,"gal_imp":gal,"adc":adc,"cal":cal,"packet":pkt})
    return jsonify(out)

# This lets the ESP32 screen replace the Nano bridge as a network uplink
# while keeping the existing serial_worker path available for fallback/testing.
@app.route("/api/device/update", methods=["POST"])
def api_device_update():
    global latest

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "msg": "Invalid JSON payload"}), 400

    device_id = data.get("device_id", None)
    if device_id is not None and not isinstance(device_id, str):
        return jsonify({"ok": False, "msg": "device_id must be a string"}), 400

    try:
        lvl_pct = _coerce_optional_float(data.get("level_pct", data.get("lvl_pct", None)), "level_pct/lvl_pct")
        gal_imp = _coerce_optional_float(data.get("gallons", data.get("gal_imp", None)), "gallons/gal_imp")
        adc = _coerce_optional_int(data.get("adc", None), "adc")
        cal = _coerce_cal_value(data.get("calibrated", data.get("cal", None)))
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

    raw = data.get("raw", None)
    if raw is not None and not isinstance(raw, str):
        return jsonify({"ok": False, "msg": "raw must be a string or null"}), 400

    if lvl_pct is None and gal_imp is None and adc is None and cal is None and not raw:
        return jsonify({"ok": False, "msg": "Payload does not contain a usable reading"}), 400

    packet = raw if raw else f"WIFI:{device_id or 'unknown'}"
    ts = datetime.now().isoformat(timespec="seconds")
    mark_bridge_seen(device_id)

    latest = {
        "last_ts": ts,
        "lvl_pct": lvl_pct,
        "gal_imp": gal_imp,
        "adc": adc,
        "cal": cal,
        "packet": packet,
    }

    db_insert(ts, lvl_pct, gal_imp, adc, cal, packet)
    auto_finalize_yesterday_once_per_day(datetime.now())

    return jsonify({"ok": True, "source": "wifi", "ts": ts})

@app.route("/api/device/command", methods=["GET"])
def api_device_command():
    device_id = (request.args.get("device_id") or BRIDGE_DEVICE_ID).strip() or BRIDGE_DEVICE_ID
    mark_bridge_seen(device_id)

    now_dt = datetime.now()
    stale_cutoff = (now_dt - timedelta(seconds=20)).isoformat(timespec="seconds")

    with cmd_lock:
        for item in cmd_queue:
            if item["device_id"] != device_id:
                continue

            # Retry a command if it was handed out but no result ever came back.
            if item["status"] == "dispatched" and (item.get("dispatch_ts") or "") < stale_cutoff:
                item["status"] = "queued"

            if item["status"] != "queued":
                continue

            item["status"] = "dispatched"
            item["dispatch_ts"] = now_dt.isoformat(timespec="seconds")
            bridge_state["last_command_ts"] = item["dispatch_ts"]
            return jsonify({
                "ok": True,
                "pending": True,
                "cmd_id": item["id"],
                "cmd": item["cmd"],
            })

    return jsonify({"ok": True, "pending": False})

@app.route("/api/device/command_result", methods=["POST"])
def api_device_command_result():
    global cmd_state

    data = request.get_json(silent=True) or {}
    device_id = (data.get("device_id") or BRIDGE_DEVICE_ID).strip() or BRIDGE_DEVICE_ID
    cmd_id = (data.get("cmd_id") or "").strip()
    cmd = (data.get("cmd") or "").strip()
    result = str(data.get("result") or "")
    ok = bool(data.get("ok", False))

    if not cmd_id:
        return jsonify({"ok": False, "msg": "cmd_id required"}), 400

    mark_bridge_seen(device_id)
    ts = datetime.now().isoformat(timespec="seconds")
    found = False

    with cmd_lock:
        for item in cmd_queue:
            if item["id"] != cmd_id:
                continue
            item["status"] = "done" if ok else "error"
            item["result"] = result
            item["result_ts"] = ts
            found = True
            if not cmd:
                cmd = item["cmd"]
            break

    cmd_state["last_cmd"] = cmd
    cmd_state["last_result"] = result or ("OK" if ok else "Command failed")
    cmd_state["last_result_ts"] = ts
    cmd_state["transport"] = "wifi_bridge"

    return jsonify({"ok": True, "matched": found, "ts": ts})

# -------- Serial command APIs --------
@app.route("/api/send_cmd", methods=["POST"])
def api_send_cmd():
    data = request.get_json(silent=True) or {}
    cmd = (data.get("cmd") or "").strip()
    result = send_command(cmd)
    return jsonify({"result": result})

@app.route("/api/cmd_status")
def api_cmd_status():
    queued = 0
    in_flight = 0
    with cmd_lock:
        for item in cmd_queue:
            if item["status"] == "queued":
                queued += 1
            elif item["status"] == "dispatched":
                in_flight += 1

    return jsonify({
        **cmd_state,
        "bridge_online": bridge_is_online(),
        "bridge_device_id": bridge_state.get("device_id"),
        "queued": queued,
        "in_flight": in_flight,
    })

@app.route("/api/calibration/empty", methods=["POST"])
def api_calibration_empty():
    return jsonify({"result": send_command("CAL_EMPTY")})

@app.route("/api/calibration/full", methods=["POST"])
def api_calibration_full():
    return jsonify({"result": send_command("CAL_FULL")})

@app.route("/api/calibration/clear", methods=["POST"])
def api_calibration_clear():
    return jsonify({"result": send_command("CLR_CAL")})

@app.route("/api/calibration/manual", methods=["POST"])
def api_calibration_manual():
    data = request.get_json(silent=True) or {}
    down_inches = max(0.0, float(data.get("down_inches", 0)))
    settings = load_settings()
    down_ft = int(down_inches // 12)
    down_in = int(round(down_inches - (down_ft * 12)))
    pct = pct_from_down_from_top(float(settings["tank_height_ft"]), down_ft, down_in)

    setting_set("baseline_pct", pct)
    ts = datetime.now().isoformat(timespec="seconds")
    setting_set("baseline_ts", ts)

    clear_result = send_command("CLR_CAL")
    baseline_result = send_command(f"SET_BASELINE {pct:.1f}")

    return jsonify({
        "ok": True,
        "baseline_pct": pct,
        "baseline_ts": ts,
        "clear_result": clear_result,
        "baseline_result": baseline_result,
    })

@app.route("/api/capture_live", methods=["POST"])
def api_capture_live():
    return jsonify({"ok": True, "status": current_status_payload()})

@app.route("/api/export_logs", methods=["POST"])
def api_export_logs():
    return jsonify({"ok": True, "download_url": "/api/export_logs.csv"})

@app.route("/api/export_logs.csv")
def api_export_logs_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ts", "lvl_pct", "gal_imp", "adc", "cal", "packet"])
    for row in db_recent(5000):
        writer.writerow(row)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cistern_readings.csv"},
    )

# -------- Level 3: Usage APIs --------
@app.route("/api/usage/recompute_today", methods=["POST"])
def api_usage_recompute_today():
    day = today_str()
    res = compute_usage_for_day(day)
    if not res:
        return jsonify({"ok": False, "msg": "Not enough samples for today"}), 200
    used, samples = res
    db_upsert_usage_day(day, used, samples)
    return jsonify({"ok": True, "day": day, "gal_used": used, "samples": samples})

@app.route("/api/usage/summary")
def api_usage_summary():
    rows = db_usage_recent(30)
    vals = [float(r[1]) for r in rows if r[1] is not None and float(r[1]) >= 0]
    avg_daily = (sum(vals) / len(vals)) if vals else None

    settings = load_settings()
    last = db_get_last_reading()
    current_gal = None
    if last:
        ts, gal_imp, lvl_pct, cal = last
        current_gal = gal_effective(lvl_pct, gal_imp, cal or 0, settings)

    days_to_empty = None
    if avg_daily and avg_daily > 0 and current_gal is not None:
        days_to_empty = current_gal / avg_daily

    out_days = [{"day": d, "gal_used": u, "samples": s} for (d, u, s) in rows]
    return jsonify({
        "avg_daily": avg_daily,
        "current_gal": current_gal,
        "days_to_empty": days_to_empty,
        "days": out_days
    })

@app.route("/api/ui2/history")
def api_ui2_history():
    days = max(1, min(365, int(request.args.get("days", 30))))
    usage_rows = db_usage_recent(days)
    usage_rows = list(reversed(usage_rows))
    level_rows = db_level_history(days)

    usage = [{"day": d, "gal_used": u, "samples": s} for (d, u, s) in usage_rows]
    level_history = [{"day": d, "ts": ts, "level_percent": lvl, "volume_imp_gal": gal} for (d, ts, lvl, gal) in level_rows]
    return jsonify({"days": days, "usage": usage, "level_history": level_history})

# -------- Level 3: Fill event APIs --------
@app.route("/api/fill/log", methods=["POST"])
def api_fill_log():
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip()
    gallons = data.get("gallons_added", None)
    note = data.get("note", None)

    if kind not in ("TRUCK_FULL", "HAUL_TRIP", "MANUAL_SET"):
        return jsonify({"ok": False, "msg": "Invalid kind"}), 400

    try:
        gallons_val = None if gallons is None or gallons == "" else float(gallons)
    except Exception:
        gallons_val = None

    db_add_fill_event(kind, gallons_val, note)
    return jsonify({"ok": True})

@app.route("/api/fill/recent")
def api_fill_recent():
    rows = db_fill_events_recent(20)
    out = [{"ts": ts, "kind": k, "gallons_added": g, "note": n} for (ts, k, g, n) in rows]
    return jsonify(out)

# -------- Level 3: Hauling plan API --------
@app.route("/api/haul/plan")
def api_haul_plan():
    settings = load_settings()
    avg_daily = usage_avg_daily(30)

    last = db_get_last_reading()
    current_gal = None
    if last:
        ts, gal_imp, lvl_pct, cal = last
        current_gal = gal_effective(lvl_pct, gal_imp, cal or 0, settings)

    if avg_daily is None or current_gal is None:
        return jsonify({"ok": False, "msg": "Need usage data + current reading", "plan": []}), 200

    tank_full = float(settings["tank_full_gal"])
    haul_tank = float(settings.get("haul_tank_gal", 600))
    low_pct   = float(settings.get("low_alert_pct", 30))
    tgt_pct   = float(settings.get("target_pct", 80))

    low_gal = (low_pct/100.0) * tank_full
    tgt_gal = (tgt_pct/100.0) * tank_full

    if current_gal >= tgt_gal:
        return jsonify({
            "ok": True,
            "avg_daily": avg_daily,
            "current_gal": current_gal,
            "tank_full": tank_full,
            "low_gal": low_gal,
            "target_gal": tgt_gal,
            "days_to_low": None,
            "trips_needed": 0,
            "days_between_trips": None,
            "plan": [],
            "msg": "Already above target"
        })

    gallons_needed = max(0.0, tgt_gal - current_gal)
    trips_needed = math.ceil(gallons_needed / haul_tank) if haul_tank > 0 else 0

    days_between = max(1, int(round(haul_tank / avg_daily))) if avg_daily > 0 else 1
    plan = []
    d = datetime.now().date()
    for i in range(trips_needed):
        plan.append({"date": d.isoformat(), "trip_number": i + 1, "gallons": haul_tank})
        d = d + timedelta(days=days_between)

    days_to_low = None
    if avg_daily > 0 and current_gal > low_gal:
        days_to_low = (current_gal - low_gal) / avg_daily
    elif current_gal <= low_gal:
        days_to_low = 0.0

    return jsonify({
        "ok": True,
        "avg_daily": avg_daily,
        "current_gal": current_gal,
        "tank_full": tank_full,
        "low_gal": low_gal,
        "target_gal": tgt_gal,
        "days_to_low": days_to_low,
        "trips_needed": trips_needed,
        "days_between_trips": days_between,
        "plan": plan,
        "msg": f"{trips_needed} trip(s) needed to reach ~{tgt_pct:.0f}%"
    })

@app.route("/ui2")
@app.route("/ui2/")
@app.route("/ui2/<path:path>")
def ui2(path="index.html"):
    if not os.path.isdir(UI2_BUILD_DIR):
        return (
            "Cistern_UI build output was not found. Run `npm install` and `npm run build` in Cistern_UI.",
            503,
        )

    requested_path = os.path.join(UI2_BUILD_DIR, path)
    if path and os.path.isfile(requested_path):
        return send_from_directory(UI2_BUILD_DIR, path)
    return send_from_directory(UI2_BUILD_DIR, "index.html")

def start_background_workers():
    # Local mode can keep using the Nano bridge over serial.
    # Cloud mode should disable this and ingest readings from /api/device/update instead.
    if ENABLE_SERIAL_WORKER:
        threading.Thread(target=serial_worker, daemon=True).start()

def create_app():
    # This factory keeps the app compatible with WSGI servers such as gunicorn.
    db_init()
    return app

application = create_app()

if __name__ == "__main__":
    create_app()
    start_background_workers()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8085")), debug=False)

