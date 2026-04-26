# windyAlarm 설계 문서

## 1. 프로그램 개요

특정 좌표의 기상 정보를 Open-Meteo API로 받아와서,
패러글라이딩에 유용한 열상승기류(thermal) 예측값을 계산·출력하는 Python 데몬.

- **단기 스레드**: N분마다 지표/900hPa 풍향풍속·기온을 콘솔에 출력
- **장기 스레드**: N분마다 폴링, 13시 KST 이후 하루 1회 내일~+6일 전체 예보 출력

## 2. 요구사항

### 2.1 기능 요구사항

- `config.txt`에서 좌표·폴링 주기·기상 모델을 읽는다.
- Open-Meteo API로 해당 좌표의 예보를 받아온다(API 키 불필요).
- 모델은 `gfs` 또는 `ecmwf` 중 선택.

**단기 스레드 (sterm)**
- `sterm`분마다 실행
- 현재 시각에 가장 가까운 타임스텝의 값을 출력
- 출력: 지표 기온, 지표 풍향·풍속, 900hPa 풍향·풍속

**장기 스레드 (lterm)**
- `lterm`분마다 폴링
- 오늘 13:00 KST 이후, 아직 오늘 실행하지 않았으면 1회 실행
- 출력 대상: 내일(+1일)~+6일, 각 날 13:00 KST 기준
- 출력 내용:
  - **API 값**: 지표 기온, 이슬점, 풍향풍속, 900hPa 풍향풍속, 구름량(하/중/상)
  - **계산값**: BL top, Cu base (LCL), W*, Hcrit, BL wind, Shear
  - Qs(태양복사량)는 날짜·시각·위도·경도·구름량으로 추정

### 2.2 비기능 요구사항

- **언어**: Python 3.9 이상
- **의존성 최소화**: `requests`, 표준 라이브러리
- **시간대**: 입력·출력 KST, API 호출/응답 내부는 UTC
- **API 키 불필요**: Open-Meteo는 비상업 용도 무료, 인증 없이 호출

### 2.3 제약 조건

- Open-Meteo의 ECMWF 데이터는 일부 압력 면(950, 900, 800hPa)이 비어 있다.
  None 필터링으로 자동 처리되며, 사용 가능한 레벨만으로 계산한다.
- GFS는 1시간 해상도, ECMWF도 동일.
- SoarCalc 원본 플러그인과 Qs 등 일부 값은 근사. 출력 시 명시.

## 3. 아키텍처

### 3.1 시스템 구조

```
windyAlarm/
├── .gitignore
├── config.txt              lat, model, sterm, lterm
├── requirements.txt        requests
├── main.py                 엔트리 포인트 (데몬 시작)
├── DESIGN.md
└── windy_alarm/
    ├── __init__.py
    ├── config.py           config.txt 로드
    ├── weather_client.py   Open-Meteo API 호출
    ├── solar.py            Qs 추정
    ├── soarcalc.py         BL top, Cu base, W*, Hcrit, BL wind, Shear
    ├── reporter.py         콘솔 출력 포맷
    └── daemon.py           단기/장기 스레드 관리
```

### 3.2 스레드 구조

```
main.py
  ├── sterm 스레드 (daemon=True)
  │     └── loop: fetch → 지표/900h 풍향풍속 출력 → sleep(sterm분)
  └── lterm 스레드 (daemon=True)
        └── loop: 13시 이후 && 오늘 미실행?
                  → fetch → 내일~+6일 전체 예보 출력
                  → sleep(lterm분)
```

### 3.3 데이터 흐름 (장기)

```
   [config.txt]
        │
        ▼
   config loader
        │
        ▼
   weather_client  ──→  GET api.open-meteo.com/v1/{gfs|ecmwf}
        │              hourly=temperature, dewpoint, wind, gh,
        │                     pressure, cloud_cover, ...
        ▼
   ForecastData (Windy 호환 형식: temp-surface, wind_u-900h, ...)
        │
        ▼
   시각 매칭  (내일 13:00 KST → UTC → 타임스텝 index)
        │
        ├──→ solar.estimate_qs  (날짜·위도·경도·구름량 → Qs)
        │
        ├──→ soarcalc.compute   (BL top, Cu base, W*, Hcrit, BL wind, Shear)
        │
        └──→ reporter.print_lterm_block
```

## 4. API/인터페이스 설계

### 4.1 외부 API: Open-Meteo

- 엔드포인트:
  - GFS: `GET https://api.open-meteo.com/v1/gfs`
  - ECMWF: `GET https://api.open-meteo.com/v1/ecmwf`
- 주요 query 파라미터:
  ```
  latitude=35.691&longitude=128.393
  hourly=temperature_2m,dewpoint_2m,wind_speed_10m,wind_direction_10m,
         surface_pressure,cloud_cover_low,cloud_cover_mid,cloud_cover_high,
         temperature_900hPa,relative_humidity_900hPa,
         wind_speed_900hPa,wind_direction_900hPa,
         geopotential_height_900hPa, ...(다른 레벨도 동일)
  wind_speed_unit=ms
  timezone=UTC
  forecast_days=7
  ```
- 응답: `hourly.time`(시각 배열) + 각 변수별 같은 길이의 값 배열,
  최상위에 `elevation`(지표 고도, m).

### 4.2 내부 변환 (Windy 호환 형식)

`weather_client._to_forecast_data`가 Open-Meteo 응답을 다음 형태로 변환한다.
이렇게 두면 daemon·soarcalc 등 다운스트림 모듈은 변경할 필요가 없다.

| 키 | 단위 | 비고 |
|---|---|---|
| `temp-{level}` | K | °C에서 변환 |
| `dewpoint-{level}` | K | 압력 면은 Magnus 공식으로 RH→이슬점 |
| `wind_u-{level}`, `wind_v-{level}` | m/s | speed+direction → u,v 성분 변환 |
| `gh-{level}` | m | 압력 면 geopotential, surface는 elevation |
| `rh-{level}` | % | |
| `pressure-surface` | Pa | hPa×100 |
| `lclouds-surface`, `mclouds-surface`, `hclouds-surface` | % | |

### 4.3 설정 파일 형식

**config.txt**
```
lat=35.691, 128.393
model=gfs           # 또는 ecmwf
sterm=10
lterm=60
```

### 4.4 출력 포맷

**단기 (sterm)**
```
[단기] 2026-04-26 14:30 KST  (GFS: 05:00 UTC)
  지표 기온: 18.3 °C
  지표 바람  : 245° / 3.2 m/s
  900hPa 바람: 260° / 5.8 m/s
············································
```

**장기 (lterm, 13시 이후 하루 1회)**
```
────────────────────────────────────────────────────────────
  windyAlarm 장기 예보 — 좌표 (35.691, 128.393)  모델: GFS
  실행: 2026-04-26 13:05 KST
────────────────────────────────────────────────────────────

[+1일] 2026-04-27 13:00 KST  (GFS: 04:00 UTC)
  ── API 값 ──────────────────────────
  지표 기온  : 18.2 °C
  지표 이슬점: 8.5 °C
  지표 바람  : 245° / 3.2 m/s
  900hPa 바람: 260° / 5.8 m/s
  구름(하/중/상): 20% / 10% / 5%
  ── 계산값 ──────────────────────────
  BL top     : 1820 m AGL
  Cu base    : 2150 m AGL  (LCL)
  W*         : 2.4 m/s
  Hcrit      : 1650 m AGL
  BL wind    : 245° / 3.3 m/s
  Shear      : 0.0120 (1/s)
...
  ※ Qs(태양복사량)는 추정값. 실제 SoarCalc과 차이가 있을 수 있습니다.
────────────────────────────────────────────────────────────
```

## 5. 검증 계획

1. **단위 테스트 (선택)**:
   - `solar.estimate_qs`: 알려진 시각·위도의 이론값과 비교
   - `soarcalc.compute`: 가짜 프로파일로 공식 결과 확인

2. **통합 테스트**:
   - 실제 좌표(35.691, 128.393)로 단발 실행
   - 단기 출력 확인 후 SoarCalc 웹과 장기 값 비교
   - GFS / ECMWF 양쪽으로 돌려 결과 비교

3. **에러 처리**:
   - Open-Meteo API 연결 실패 (스레드는 오류 출력 후 다음 주기 재시도)
   - ECMWF의 일부 레벨이 비어 있는 경우 (None 필터링이 자동 처리)
   - 응답 형식이 예상과 다른 경우

## 6. 위험 요소 및 주의사항

- **SoarCalc 완전 재현은 아님**: Qs는 추정값. 1차 구현 후 원본 소스와 비교·보정 필요
- **모델별 해상도 차이**: ECMWF는 일부 압력 면이 비어 있어 GFS보다 거친 BL 계산이 됨
- **Open-Meteo 무료 한도**: 일 10,000 호출 제한이 있다(비상업). 단기 10분 + 장기 60분 주기면
  하루 약 168회 + 24회 = 200회 미만으로 안전한 수준
