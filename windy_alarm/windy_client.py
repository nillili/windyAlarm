import requests
from dataclasses import dataclass


LEVELS = ["surface", "1000h", "950h", "925h", "900h", "850h", "800h", "700h", "600h", "500h"]
PARAMETERS = ["wind", "temp", "dewpoint", "rh", "gh", "pressure", "lclouds", "mclouds", "hclouds"]
API_URL = "https://api.windy.com/api/point-forecast/v2"


@dataclass
class ForecastData:
    timestamps: list       # UTC ms
    data: dict             # {"temp-surface": [...], "wind_u-850h": [...], ...}


def fetch_forecast(lat: float, lon: float, api_key: str) -> ForecastData:
    payload = {
        "lat": lat,
        "lon": lon,
        "model": "gfs",
        "parameters": PARAMETERS,
        "levels": LEVELS,
        "key": api_key,
    }
    resp = requests.post(API_URL, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Windy API 오류 {resp.status_code}: {resp.text}")

    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"Windy API 오류: {body['error']}")

    timestamps = body.get("ts", [])
    data = {k: v for k, v in body.items() if k != "ts" and k != "units" and k != "warning"}

    return ForecastData(timestamps=timestamps, data=data)


def find_time_index(timestamps: list, target_utc_ms: int) -> int:
    """타임스탬프 리스트에서 target에 가장 가까운 인덱스를 반환."""
    return min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - target_utc_ms))
