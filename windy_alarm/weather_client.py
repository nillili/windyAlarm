import math
import requests
from dataclasses import dataclass
from datetime import datetime


PRESSURE_LEVELS = [1000, 950, 925, 900, 850, 800, 700, 600, 500]
LEVELS = ["surface"] + [f"{p}h" for p in PRESSURE_LEVELS]

API_BASE = "https://api.open-meteo.com/v1"
MODEL_ENDPOINTS = {
    "gfs": "/gfs",
    "ecmwf": "/ecmwf",
}


@dataclass
class ForecastData:
    timestamps: list   # UTC ms
    data: dict         # {"temp-surface": [...], "wind_u-900h": [...], ...}


def fetch_forecast(lat: float, lon: float, model: str = "gfs") -> ForecastData:
    if model not in MODEL_ENDPOINTS:
        raise ValueError(f"지원하지 않는 모델: {model}")

    url = f"{API_BASE}{MODEL_ENDPOINTS[model]}"

    hourly_vars = [
        "temperature_2m", "dewpoint_2m",
        "wind_speed_10m", "wind_direction_10m",
        "surface_pressure",
        "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    ]
    for p in PRESSURE_LEVELS:
        hourly_vars.extend([
            f"temperature_{p}hPa",
            f"relative_humidity_{p}hPa",
            f"wind_speed_{p}hPa",
            f"wind_direction_{p}hPa",
            f"geopotential_height_{p}hPa",
        ])

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(hourly_vars),
        "wind_speed_unit": "ms",
        "timezone": "UTC",
        "forecast_days": 7,
    }

    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Open-Meteo API 오류 {resp.status_code}: {resp.text}")

    body = resp.json()
    if body.get("error"):
        raise RuntimeError(f"Open-Meteo API 오류: {body.get('reason', '')}")

    return _to_forecast_data(body)


def find_time_index(timestamps: list, target_utc_ms: int) -> int:
    return min(range(len(timestamps)),
               key=lambda i: abs(timestamps[i] - target_utc_ms))


# ──────────────────────────────────────────────
# 응답 → ForecastData 변환
# ──────────────────────────────────────────────

def _to_forecast_data(body: dict) -> ForecastData:
    hourly = body.get("hourly", {})
    times = hourly.get("time", [])
    elevation = body.get("elevation", 0.0)

    timestamps = [_iso_to_utc_ms(t) for t in times]
    n = len(timestamps)
    data = {}

    # ── 지표 ──
    if "temperature_2m" in hourly:
        data["temp-surface"] = _c_to_k_list(hourly["temperature_2m"])
    if "dewpoint_2m" in hourly:
        data["dewpoint-surface"] = _c_to_k_list(hourly["dewpoint_2m"])
    if "surface_pressure" in hourly:
        data["pressure-surface"] = [
            p * 100.0 if p is not None else None for p in hourly["surface_pressure"]
        ]
    if "wind_speed_10m" in hourly and "wind_direction_10m" in hourly:
        u, v = _wind_uv_arrays(hourly["wind_speed_10m"], hourly["wind_direction_10m"])
        data["wind_u-surface"] = u
        data["wind_v-surface"] = v

    # 구름량
    for word, prefix in (("low", "l"), ("mid", "m"), ("high", "h")):
        key_in = f"cloud_cover_{word}"
        if key_in in hourly:
            data[f"{prefix}clouds-surface"] = list(hourly[key_in])

    # 지표 고도: Open-Meteo 응답 최상위의 elevation 값을 길이만큼 채워 둔다
    data["gh-surface"] = [float(elevation)] * n

    # ── 압력 면 ──
    for p in PRESSURE_LEVELS:
        level = f"{p}h"
        t_in = f"temperature_{p}hPa"
        rh_in = f"relative_humidity_{p}hPa"
        ws_in = f"wind_speed_{p}hPa"
        wd_in = f"wind_direction_{p}hPa"
        gh_in = f"geopotential_height_{p}hPa"

        if t_in in hourly:
            data[f"temp-{level}"] = _c_to_k_list(hourly[t_in])
        if rh_in in hourly:
            data[f"rh-{level}"] = list(hourly[rh_in])
        if t_in in hourly and rh_in in hourly:
            data[f"dewpoint-{level}"] = [
                _dewpoint_k(t, rh)
                for t, rh in zip(hourly[t_in], hourly[rh_in])
            ]
        if ws_in in hourly and wd_in in hourly:
            u, v = _wind_uv_arrays(hourly[ws_in], hourly[wd_in])
            data[f"wind_u-{level}"] = u
            data[f"wind_v-{level}"] = v
        if gh_in in hourly:
            data[f"gh-{level}"] = list(hourly[gh_in])

    return ForecastData(timestamps=timestamps, data=data)


def _iso_to_utc_ms(iso_str: str) -> int:
    """Open-Meteo 시각 문자열(ISO 8601, timezone=UTC면 naive)을 UTC 밀리초로."""
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    elif "+" not in iso_str[10:] and "-" not in iso_str[10:]:
        iso_str = iso_str + "+00:00"
    return int(datetime.fromisoformat(iso_str).timestamp() * 1000)


def _c_to_k_list(values):
    return [v + 273.15 if v is not None else None for v in values]


def _wind_uv_arrays(speeds, directions):
    """speed(m/s) + 풍향(°, 어디서 부는가) → u(동), v(북) 성분 배열."""
    u_list, v_list = [], []
    for spd, dir_deg in zip(speeds, directions):
        if spd is None or dir_deg is None:
            u_list.append(None)
            v_list.append(None)
            continue
        rad = math.radians(dir_deg)
        u_list.append(-spd * math.sin(rad))
        v_list.append(-spd * math.cos(rad))
    return u_list, v_list


def _dewpoint_k(t_c, rh):
    """Magnus 공식: 기온(°C) + 상대습도(%) → 이슬점(K)."""
    if t_c is None or rh is None or rh <= 0:
        return None
    a, b = 17.625, 243.04
    gamma = (a * t_c) / (b + t_c) + math.log(rh / 100.0)
    td_c = (b * gamma) / (a - gamma)
    return td_c + 273.15
