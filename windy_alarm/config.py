from dataclasses import dataclass


SUPPORTED_MODELS = {"gfs", "ecmwf"}


@dataclass
class Config:
    lat: float
    lon: float
    sterm: int   # 단기 폴링 주기 (분)
    lterm: int   # 장기 폴링 주기 (분)
    model: str   # "gfs" 또는 "ecmwf"


def load_config(config_path="config.txt") -> Config:
    lat = lon = None
    sterm = 10
    lterm = 60
    model = "gfs"

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
            elif key == "model":
                v = value.lower()
                if v not in SUPPORTED_MODELS:
                    raise ValueError(f"지원하지 않는 모델: {value} (gfs 또는 ecmwf)")
                model = v

    if lat is None or lon is None:
        raise ValueError("config.txt에 lat 항목이 없습니다.")

    return Config(lat=lat, lon=lon, sterm=sterm, lterm=lterm, model=model)
