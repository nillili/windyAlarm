from datetime import datetime
from .soarcalc import SoarResult

SEP  = "─" * 60
SEP2 = "·" * 60


# ──────────────────────────────────────────────
# 단기 출력
# ──────────────────────────────────────────────

def print_sterm(local_dt: datetime, matched_utc: datetime,
                sfc_temp_c, sfc_dir, sfc_spd, h900_dir, h900_spd):
    matched_str = matched_utc.strftime("%H:%M UTC")
    print(f"\n[단기] {local_dt.strftime('%Y-%m-%d %H:%M')} KST  (GFS: {matched_str})")
    if sfc_temp_c is None:
        print("  지표 기온: —")
    else:
        print(f"  지표 기온: {sfc_temp_c:.1f} °C")
    _wind_line("지표 바람  ", sfc_dir,  sfc_spd)
    _wind_line("900hPa 바람", h900_dir, h900_spd)
    print(SEP2)


# 8방위 화살표. 바람이 불어나가는 방향(목적지)을 가리킨다.
# 북풍(0°)=남쪽으로 불어감=↓, 동풍(90°)=서쪽으로=←, 남풍(180°)=북쪽으로=↑
_ARROWS = ["↓", "↙", "←", "↖", "↑", "↗", "→", "↘"]


def _arrow(direction):
    if direction is None:
        return "·"
    idx = int((direction + 22.5) // 45) % 8
    return _ARROWS[idx]


def _wind_line(label: str, direction, speed):
    if direction is None:
        print(f"  {label}: —")
    else:
        print(f"  {label}: {_arrow(direction)}  {direction:>3}° / {speed} m/s")


# ──────────────────────────────────────────────
# 장기 출력
# ──────────────────────────────────────────────

def print_lterm_header(lat: float, lon: float, now_kst: datetime):
    print(f"\n{SEP}")
    print(f"  windyAlarm 장기 예보 — 좌표 ({lat}, {lon})  모델: GFS")
    print(f"  실행: {now_kst.strftime('%Y-%m-%d %H:%M')} KST")
    print(SEP)


def print_lterm_block(day_offset: int, target_kst: datetime, matched_utc: datetime,
                      raw: dict, result: SoarResult):
    matched_str = matched_utc.strftime("%H:%M UTC")
    label = "[오늘]" if day_offset == 0 else f"[+{day_offset}일]"
    print(f"\n{label} {target_kst.strftime('%Y-%m-%d')} 13:00 KST  (GFS: {matched_str})")

    print("  ── API 값 ──────────────────────────")
    print(f"  지표 기온  : {raw['sfc_temp_c']} °C")
    print(f"  지표 이슬점: {raw['sfc_dew_c']} °C")
    _wind_line("지표 바람  ", raw['sfc_dir'],  raw['sfc_spd'])
    _wind_line("900hPa 바람", raw['h900_dir'], raw['h900_spd'])
    lc = raw['lclouds']
    mc = raw['mclouds']
    hc = raw['hclouds']
    print(f"  구름(하/중/상): {lc}% / {mc}% / {hc}%")

    print("  ── 계산값 ──────────────────────────")
    print(f"  BL top     : {result.bl_top} m AGL")
    if result.cu_base is not None:
        print(f"  Cu base    : {result.cu_base} m AGL  (LCL)")
    else:
        print(f"  Cu base    : — (적운 없음)")
    print(f"  W*         : {result.w_star} m/s")
    print(f"  Hcrit      : {result.h_crit} m AGL")
    print(f"  BL wind    : {_arrow(result.bl_wind_dir)}  {result.bl_wind_dir}° / {result.bl_wind_speed} m/s")
    print(f"  Shear      : {result.shear} (1/s)")


def print_lterm_footer():
    print()
    print("  ※ Qs(태양복사량)는 추정값. 실제 SoarCalc과 차이가 있을 수 있습니다.")
    print(SEP)
