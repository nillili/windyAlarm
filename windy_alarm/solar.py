import math
from datetime import datetime


def estimate_qs(dt_utc: datetime, lat: float, lon: float, cloud_cover: float) -> float:
    """
    태양복사량 추정 (W/m²).
    cloud_cover: 0.0 ~ 1.0 (0=맑음, 1=완전구름)
    """
    doy = dt_utc.timetuple().tm_yday
    hour_utc = dt_utc.hour + dt_utc.minute / 60.0

    # 태양 적위 (declination)
    decl = math.radians(23.45 * math.sin(math.radians(360 / 365 * (doy - 81))))
    lat_r = math.radians(lat)

    # 시간각: 지방태양시(LST) 기준. LST = UTC + lon/15
    lst_hour = hour_utc + lon / 15.0
    hour_angle = math.radians(15 * (lst_hour - 12))

    # 태양 고도각
    sin_elev = (math.sin(lat_r) * math.sin(decl)
                + math.cos(lat_r) * math.cos(decl) * math.cos(hour_angle))
    sin_elev = max(0.0, sin_elev)

    # 대기 외 복사량 (W/m²), 지구-태양 거리 보정 포함
    e0 = 1 + 0.033 * math.cos(math.radians(360 / 365 * doy))
    s0 = 1361.0  # 태양상수
    qs_clear = s0 * e0 * sin_elev * 0.75  # 대기투과율 0.75 근사

    # 구름 감쇠
    qs = qs_clear * (1.0 - 0.75 * cloud_cover ** 3.4)
    return max(0.0, qs)
