# windyAlarm

패러글라이딩을 위한 기상 예보 데몬. Open-Meteo API(GFS/ECMWF)로 지정 좌표의 기상 데이터를 받아,
지표/900hPa 풍향풍속과 열상승기류(BL top, Cu base, W*, Hcrit) 계산값을 주기적으로 출력한다.

## 설치

```bash
conda create -n windy python=3.11
conda activate windy
pip install -r requirements.txt
```

## 설정

`config.txt`에서 좌표, 모델, 폴링 주기를 설정한다.

```
lat=35.691, 128.393   # 위도, 경도
model=gfs             # gfs 또는 ecmwf
sterm=10              # 단기 스레드 주기 (분)
lterm=60              # 장기 스레드 주기 (분)
```

## 실행

```bash
conda activate windy
python main.py
```

종료: `Ctrl+C`
