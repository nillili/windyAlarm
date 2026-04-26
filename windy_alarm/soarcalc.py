import math
from dataclasses import dataclass


@dataclass
class AtmProfile:
    """고도 레벨별 대기 프로파일 (surface 포함)."""
    heights: list       # m ASL, surface부터 상층까지
    temps: list         # K
    dewpoints: list     # K
    wind_u: list        # m/s (동서)
    wind_v: list        # m/s (남북)
    surface_pressure: float  # hPa
    surface_height: float    # m ASL (지형 고도)


@dataclass
class SoarResult:
    bl_top: float        # m AGL
    cu_base: float       # m AGL (LCL), None이면 적운 없음
    w_star: float        # m/s
    h_crit: float        # m AGL
    bl_wind_dir: float   # °
    bl_wind_speed: float # m/s
    shear: float         # 1/s


# 열역학 상수
GAMMA_DRY = 9.8e-3   # K/m (건조단열감율)
GAMMA_SAT = 6.5e-3   # K/m (습윤단열감율 근사)
CP = 1005.0
G = 9.81


def _lcl_height(t_surface_k: float, td_surface_k: float) -> float:
    """LCL 고도 (m AGL). 기온-이슬점 차이 기반."""
    spread = t_surface_k - td_surface_k
    return max(0.0, spread * 122.0)  # 경험 공식: ~122 m/°C


def _find_bl_top(heights_agl: list, temps_k: list, t_surface_k: float) -> float:
    """
    지표 공기덩이를 건조단열로 상승시켜 환경기온과 교차하는 고도 = BL top.
    """
    for i in range(1, len(heights_agl)):
        parcel_t = t_surface_k - GAMMA_DRY * heights_agl[i]
        if parcel_t <= temps_k[i]:
            # 선형 보간
            dh = heights_agl[i] - heights_agl[i - 1]
            prev_parcel = t_surface_k - GAMMA_DRY * heights_agl[i - 1]
            dt_env = temps_k[i] - temps_k[i - 1]
            dt_par = parcel_t - prev_parcel
            frac = (prev_parcel - temps_k[i - 1]) / ((dt_env - dt_par) + 1e-9)
            return heights_agl[i - 1] + frac * dh
    return heights_agl[-1]


def _w_star(bl_top_m: float, qs: float, t_surface_k: float) -> float:
    """열상승 속도 W* (m/s). Deardorff (1970) 공식."""
    if bl_top_m <= 0 or qs <= 0:
        return 0.0
    heat_flux = qs / (CP * 1.2)  # 밀도 1.2 kg/m³ 근사
    w3 = G / t_surface_k * heat_flux * bl_top_m
    return max(0.0, w3 ** (1 / 3))


def _h_crit(heights_agl: list, temps_k: list, t_surface_k: float) -> float:
    """상승 공기덩이의 부력이 사라지는 고도 (Hcrit 근사)."""
    for h in range(10, int(heights_agl[-1]), 10):
        parcel_t = t_surface_k - GAMMA_DRY * h
        env_t = _interp(heights_agl, temps_k, h)
        if parcel_t < env_t:
            return float(h)
    return heights_agl[-1]


def _bl_wind(heights_agl: list, wind_u: list, wind_v: list, bl_top: float):
    """경계층 평균 풍향·풍속."""
    us, vs = [], []
    for i, h in enumerate(heights_agl):
        if h <= bl_top:
            us.append(wind_u[i])
            vs.append(wind_v[i])
    if not us:
        us, vs = [wind_u[0]], [wind_v[0]]
    u_mean = sum(us) / len(us)
    v_mean = sum(vs) / len(vs)
    speed = math.hypot(u_mean, v_mean)
    direction = (math.degrees(math.atan2(u_mean, v_mean)) + 180) % 360
    return direction, speed


def _shear(heights_agl: list, wind_u: list, wind_v: list, bl_top: float) -> float:
    """경계층 내 윈드 시어 (1/s)."""
    if bl_top <= 0:
        return 0.0
    speeds = []
    hs = []
    for i, h in enumerate(heights_agl):
        if h <= bl_top:
            speeds.append(math.hypot(wind_u[i], wind_v[i]))
            hs.append(h)
    if len(speeds) < 2:
        return 0.0
    dv = abs(speeds[-1] - speeds[0])
    dh = hs[-1] - hs[0]
    return dv / dh if dh > 0 else 0.0


def _interp(xs: list, ys: list, x: float) -> float:
    """단순 선형 보간."""
    for i in range(1, len(xs)):
        if xs[i] >= x:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1] + 1e-9)
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def compute(profile: AtmProfile, qs: float) -> SoarResult:
    sfc_h = profile.surface_height
    heights_agl = [max(0.0, h - sfc_h) for h in profile.heights]
    t_surface_k = profile.temps[0]
    td_surface_k = profile.dewpoints[0]

    bl_top = _find_bl_top(heights_agl, profile.temps, t_surface_k)
    cu_base = _lcl_height(t_surface_k, td_surface_k)
    cu_base = cu_base if cu_base < bl_top * 1.5 else None

    w = _w_star(bl_top, qs, t_surface_k)
    h_crit = _h_crit(heights_agl, profile.temps, t_surface_k)
    bl_dir, bl_speed = _bl_wind(heights_agl, profile.wind_u, profile.wind_v, bl_top)
    shear = _shear(heights_agl, profile.wind_u, profile.wind_v, bl_top)

    return SoarResult(
        bl_top=round(bl_top),
        cu_base=round(cu_base) if cu_base is not None else None,
        w_star=round(w, 1),
        h_crit=round(h_crit),
        bl_wind_dir=round(bl_dir),
        bl_wind_speed=round(bl_speed, 1),
        shear=round(shear, 4),
    )
