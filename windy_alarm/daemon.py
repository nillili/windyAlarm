import math
import time
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import Config
from .weather_client import fetch_forecast, find_time_index, LEVELS as LEVEL_ORDER
from .solar import estimate_qs
from .soarcalc import compute, AtmProfile
from . import reporter

KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc

LTERM_TRIGGER_HOUR = 13  # 장기 예보 실행 기준 시각 (KST)


def _get_field(data: dict, param: str, level: str) -> list:
    return data.get(f"{param}-{level}", [])


def _surface_height(data: dict) -> float:
    gh = _get_field(data, "gh", "surface")
    if gh:
        for v in gh:
            if v is not None:
                return float(v)
    return 0.0


def _build_profile(data: dict, idx: int, surface_height: float) -> AtmProfile:
    heights, temps, dewpoints, wind_u, wind_v = [], [], [], [], []

    # 지표값을 먼저 넣는다 (gh-surface는 없는 경우가 많아 surface_height로 대체)
    sfc_temp = _get_field(data, "temp",     "surface")
    sfc_dew  = _get_field(data, "dewpoint", "surface")
    sfc_wu   = _get_field(data, "wind_u",   "surface")
    sfc_wv   = _get_field(data, "wind_v",   "surface")
    if sfc_temp and sfc_dew and sfc_wu and sfc_wv \
       and None not in (sfc_temp[idx], sfc_dew[idx], sfc_wu[idx], sfc_wv[idx]):
        heights.append(surface_height)
        temps.append(sfc_temp[idx])
        dewpoints.append(sfc_dew[idx])
        wind_u.append(sfc_wu[idx])
        wind_v.append(sfc_wv[idx])

    # 압력 레벨 (surface 제외)
    for level in LEVEL_ORDER:
        if level == "surface":
            continue
        gh   = _get_field(data, "gh",       level)
        temp = _get_field(data, "temp",     level)
        dew  = _get_field(data, "dewpoint", level)
        wu   = _get_field(data, "wind_u",   level)
        wv   = _get_field(data, "wind_v",   level)
        if not (gh and temp and dew and wu and wv):
            continue
        vals = (gh[idx], temp[idx], dew[idx], wu[idx], wv[idx])
        if None in vals:
            continue
        if vals[0] <= surface_height:  # 지표 아래 레벨은 스킵
            continue
        heights.append(gh[idx])
        temps.append(temp[idx])
        dewpoints.append(dew[idx])
        wind_u.append(wu[idx])
        wind_v.append(wv[idx])

    sfc_p = _get_field(data, "pressure", "surface")
    p = (sfc_p[idx] / 100.0) if (sfc_p and sfc_p[idx] is not None) else 1013.25

    return AtmProfile(
        heights=heights, temps=temps, dewpoints=dewpoints,
        wind_u=wind_u, wind_v=wind_v,
        surface_pressure=p, surface_height=surface_height,
    )


def _day_max_surface_temp(data: dict, timestamps: list, target_utc_ms: int,
                          window_hours: int = 4) -> float:
    """target 시각 ± window 내 지표 기온의 최댓값 (K)."""
    temps = _get_field(data, "temp", "surface")
    if not temps:
        return None
    window_ms = window_hours * 3600 * 1000
    tmax = None
    for ts, t in zip(timestamps, temps):
        if t is None:
            continue
        if abs(ts - target_utc_ms) <= window_ms:
            if tmax is None or t > tmax:
                tmax = t
    return tmax


def _cloud_cover(data: dict, idx: int) -> float:
    vals = []
    for param in ("lclouds", "mclouds", "hclouds"):
        f = _get_field(data, param, "surface")
        if f:
            vals.append(f[idx] / 100.0)
    return min(1.0, max(vals) if vals else 0.0)


def _wind_info(data: dict, idx: int, level: str):
    """(direction°, speed m/s) 반환."""
    wu = _get_field(data, "wind_u", level)
    wv = _get_field(data, "wind_v", level)
    if not (wu and wv):
        return None, None
    u, v = wu[idx], wv[idx]
    if u is None or v is None:
        return None, None
    speed = math.hypot(u, v)
    direction = (math.degrees(math.atan2(u, v)) + 180) % 360
    return round(direction), round(speed, 1)


# ──────────────────────────────────────────────
# 단기 스레드
# ──────────────────────────────────────────────

def short_term_worker(cfg: Config):
    while True:
        try:
            now_utc = datetime.now(UTC)
            now_utc_ms = int(now_utc.timestamp() * 1000)

            forecast = fetch_forecast(cfg.lat, cfg.lon, cfg.model)
            idx = find_time_index(forecast.timestamps, now_utc_ms)
            matched_utc = datetime.fromtimestamp(forecast.timestamps[idx] / 1000, tz=UTC)

            sfc_dir, sfc_spd = _wind_info(forecast.data, idx, "surface")
            h900_dir, h900_spd = _wind_info(forecast.data, idx, "900h")

            sfc_temp = _get_field(forecast.data, "temp", "surface")
            sfc_temp_c = (sfc_temp[idx] - 273.15) if (sfc_temp and sfc_temp[idx] is not None) else None

            reporter.print_sterm(
                local_dt=datetime.now(KST),
                matched_utc=matched_utc,
                sfc_temp_c=sfc_temp_c,
                sfc_dir=sfc_dir, sfc_spd=sfc_spd,
                h900_dir=h900_dir, h900_spd=h900_spd,
            )
        except Exception as e:
            print(f"[단기 오류] {e}")

        time.sleep(cfg.sterm * 60)


# ──────────────────────────────────────────────
# 장기 스레드
# ──────────────────────────────────────────────

def long_term_worker(cfg: Config):
    while True:
        try:
            now_kst = datetime.now(KST)

            day_offsets = list(range(1, 7))             # +1 ~ +6은 항상
            if now_kst.hour < LTERM_TRIGGER_HOUR:
                day_offsets = [0] + day_offsets         # 13시 전이면 오늘도 포함

            _run_long_term(cfg, now_kst, day_offsets)
        except Exception as e:
            print(f"[장기 오류] {e}")

        time.sleep(cfg.lterm * 60)


def _run_long_term(cfg: Config, now_kst: datetime, day_offsets: list):
    forecast = fetch_forecast(cfg.lat, cfg.lon, cfg.model)
    sfc_h = _surface_height(forecast.data)

    reporter.print_lterm_header(cfg.lat, cfg.lon, now_kst)

    today_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)

    for day_offset in day_offsets:
        target_kst = today_kst + timedelta(days=day_offset, hours=13)
        target_utc = target_kst.astimezone(UTC)
        target_ms = int(target_utc.timestamp() * 1000)

        idx = find_time_index(forecast.timestamps, target_ms)
        matched_utc = datetime.fromtimestamp(forecast.timestamps[idx] / 1000, tz=UTC)

        profile = _build_profile(forecast.data, idx, sfc_h)
        if not profile.temps:
            label = "오늘" if day_offset == 0 else f"+{day_offset}일"
            print(f"  [{label}] 데이터 부족으로 건너뜀")
            continue

        # 지표 기온을 하루 최댓값으로 대체 (대류 최성기 기준)
        tmax = _day_max_surface_temp(forecast.data, forecast.timestamps, target_ms)
        if tmax is not None and tmax > profile.temps[0]:
            profile.temps[0] = tmax

        cloud = _cloud_cover(forecast.data, idx)
        qs = estimate_qs(matched_utc, cfg.lat, cfg.lon, cloud)
        result = compute(profile, qs)

        # raw API 값 수집
        raw = _collect_raw(forecast.data, idx)

        reporter.print_lterm_block(
            day_offset=day_offset,
            target_kst=target_kst,
            matched_utc=matched_utc,
            raw=raw,
            result=result,
        )

    reporter.print_lterm_footer()


def _collect_raw(data: dict, idx: int) -> dict:
    """장기 블록에 표시할 raw API 값."""
    def val(param, level):
        f = _get_field(data, param, level)
        return f[idx] if f else None

    sfc_temp_k = val("temp", "surface")
    sfc_dew_k  = val("dewpoint", "surface")
    sfc_wu     = val("wind_u", "surface")
    sfc_wv     = val("wind_v", "surface")
    h900_wu    = val("wind_u", "900h")
    h900_wv    = val("wind_v", "900h")
    lc = val("lclouds", "surface")
    mc = val("mclouds", "surface")
    hc = val("hclouds", "surface")

    def wind(u, v):
        if u is None or v is None:
            return None, None
        spd = math.hypot(u, v)
        dirr = (math.degrees(math.atan2(u, v)) + 180) % 360
        return round(dirr), round(spd, 1)

    sfc_dir, sfc_spd = wind(sfc_wu, sfc_wv)
    h900_dir, h900_spd = wind(h900_wu, h900_wv)

    return {
        "sfc_temp_c": round(sfc_temp_k - 273.15, 1) if sfc_temp_k else None,
        "sfc_dew_c":  round(sfc_dew_k  - 273.15, 1) if sfc_dew_k  else None,
        "sfc_dir": sfc_dir, "sfc_spd": sfc_spd,
        "h900_dir": h900_dir, "h900_spd": h900_spd,
        "lclouds": round(lc) if lc is not None else None,
        "mclouds": round(mc) if mc is not None else None,
        "hclouds": round(hc) if hc is not None else None,
    }


# ──────────────────────────────────────────────
# 데몬 시작
# ──────────────────────────────────────────────

def start(cfg: Config):
    t_short = threading.Thread(target=short_term_worker, args=(cfg,), daemon=True, name="sterm")
    t_long  = threading.Thread(target=long_term_worker,  args=(cfg,), daemon=True, name="lterm")
    t_short.start()
    time.sleep(5)  # 단기 출력이 먼저 자리 잡도록 5초 지연 후 장기 시작
    t_long.start()
    return t_short, t_long
