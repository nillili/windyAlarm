import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    lat: float
    lon: float
    sterm: int   # 단기 폴링 주기 (분)
    lterm: int   # 장기 폴링 주기 (분)
    api_key: str


def load_config(config_path="config.txt") -> Config:
    load_dotenv()
    api_key = os.getenv("WINDY_API_KEY", "").strip()
    if not api_key:
        raise ValueError(".env 파일에 WINDY_API_KEY가 없습니다.")

    lat = lon = None
    sterm = 10
    lterm = 60

    with open(config_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if key == "lat":
                parts = [p.strip() for p in value.split(",")]
                lat, lon = float(parts[0]), float(parts[1])
            elif key == "sterm":
                sterm = int(value)
            elif key == "lterm":
                lterm = int(value)

    if lat is None or lon is None:
        raise ValueError("config.txt에 lat 항목이 없습니다.")

    return Config(lat=lat, lon=lon, sterm=sterm, lterm=lterm, api_key=api_key)
