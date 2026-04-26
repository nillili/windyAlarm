import time
from windy_alarm.config import load_config
from windy_alarm import daemon

def main():
    cfg = load_config()
    print(f"windyAlarm 시작 — 좌표 ({cfg.lat}, {cfg.lon})")
    print(f"  단기: {cfg.sterm}분마다 지표/900h 풍향풍속")
    print(f"  장기: {cfg.lterm}분마다 체크, 13시 이후 하루 1회 7일 예보")
    print("  종료: Ctrl+C")

    t_short, t_long = daemon.start(cfg)

    try:
        while t_short.is_alive() and t_long.is_alive():
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nwindyAlarm 종료.")

if __name__ == "__main__":
    main()
