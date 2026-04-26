# windyAlarm 설계 문서

## 1. 프로그램 개요

특정 좌표의 기상 정보를 Windy Point Forecast API로 받아와서,
패러글라이딩에 유용한 열상승기류(thermal) 예측값을 계산·출력하는 Python 데몬.

- **단기 스레드**: N분마다 지표/900hPa 풍향풍속을 콘솔에 출력
- **장기 스레드**: N분마다 폴링, 13시 KST 이후 하루 1회 내일~+6일 전체 예보 출력

## 2. 요구사항

### 2.1 기능 요구사항

- `config.txt`에서 좌표와 폴링 주기를 읽는다.
- `.env`에서 Windy API 키를 읽는다.
- Windy Point Forecast API(모델: GFS)로 해당 좌표의 예보를 받아온다.

**단기 스레드 (sterm)**
- `sterm`분마다 실행
- 현재 시각에 가장 가까운 GFS 타임스텝의 값을 출력
- 출력: 지표 풍향·풍속, 900hPa 풍향·풍속

**장기 스레드 (lterm)**
- `lterm`분마다 폴링
- 오늘 13:00 KST 이후, 아직 오늘 실행하지 않았으면 1회 실행
- 출력 대상: 내일(+1일)~+6일, 각 날 13:00 KST 기준
- 출력 내용:
  - **API 값**: 지표 기온, 이슬점, 풍향풍속, 900hPa 풍향풍속, 구름량(하/중/상)
  - **계산값**: BL top, Cu base (LCL), W*, Hcrit, BL wind, Shear
  - Qs(태양복사량)는 날짜·시각·위도·구름량으로 추정

### 2.2 비기능 요구사항

- **언어**: Python 3.9 이상
- **의존성 최소화**: `requests`, `python-dotenv`, 표준 라이브러리
- **시간대**: 입력·출력 KST, API 호출/응답 내부는 UTC
- **구성 파일은 git에 안전하게 올릴 수 있어야 함** (`.env`는 `.gitignore`)

### 2.3 제약 조건

- Windy Point Forecast API는 ECMWF 미지원 → GFS 고정
- GFS 시간 해상도 3시간 → 요청 시각은 가장 가까운 타임스텝으로 매칭
- SoarCalc 원본 플러그인과 Qs 등 일부 값은 근사. 출력 시 명시

## 3. 아키텍처

### 3.1 시스템 구조

```
windyAlarm/
├── .env                    API 키 (gitignore)
├── .env.example            템플릿
├── .gitignore
├── config.txt              lat, sterm, lterm
├── requirements.txt
├── main.py                 엔트리 포인트 (데몬 시작)
├── DESIGN.md
└── windy_alarm/
    ├── __init__.py
    ├── config.py           config.txt + .env 로드
    ├── windy_client.py     Windy API 호출
    ├── solar.py            Qs 추정
    ├── soarcalc.py         BL top, Cu base, W*, Hcrit, BL wind, shear
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
[config.txt] [.env]
      │         │
      ▼         ▼
  config loader
      │
      ▼
  windy_client  ──→  POST api.windy.com/api/point-forecast/v2
      │               model=gfs, levels=surface~500h
      ▼
  시각 매칭  (내일 13:00 KST → UTC → GFS 타임스텝 index)
      │
      ├──→ solar.estimate_qs  (날짜·위도·구름량 → Qs)
      │
      ├──→ soarcalc.compute   (BL top, Cu base, W*, Hcrit, BL wind, Shear)
      │
      └──→ reporter.print_lterm_block
```

## 4. API/인터페이스 설계

### 4.1 외부 API: Windy Point Forecast v2

- 엔드포인트: `POST https://api.windy.com/api/point-forecast/v2`
- 요청:
  ```json
  {
    "lat": 35.685, "lon": 128.413,
    "model": "gfs",
    "parameters": ["wind","temp","dewpoint","rh","gh","pressure",
                   "lclouds","mclouds","hclouds"],
    "levels": ["surface","1000h","950h","925h","900h","850h","800h",
               "700h","600h","500h"],
    "key": "<API_KEY>"
  }
  ```

### 4.2 설정 파일 형식

**config.txt**
```
lat=35.685, 128.413
sterm=10
lterm=60
```

**.env**
```
WINDY_API_KEY=your_key_here
```

### 4.3 출력 포맷

**단기 (sterm)**
```
[단기] 2026-04-24 14:30 KST  (GFS: 05:00 UTC)
  지표   :  245° / 3.2 m/s
  900hPa :  260° / 5.8 m/s
············································
```

**장기 (lterm, 13시 이후 하루 1회)**
```
────────────────────────────────────────────────────────────
  windyAlarm 장기 예보 — 좌표 (35.685, 128.413)  모델: GFS
  실행: 2026-04-24 13:05 KST
────────────────────────────────────────────────────────────

[+1일] 2026-04-25 13:00 KST  (GFS: 04:00 UTC)
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
   - 실제 좌표(35.685, 128.413)로 단발 실행
   - 단기 출력 확인 후 SoarCalc 웹과 장기 값 비교

3. **에러 처리**:
   - API 키 누락·오류
   - 네트워크 실패 (스레드는 오류 출력 후 다음 주기 재시도)
   - dtime이 GFS 예보 범위 초과

## 6. 위험 요소 및 주의사항

- **SoarCalc 완전 재현은 아님**: Qs는 추정값. 1차 구현 후 원본 소스와 비교·보정 필요
- **GFS 시간 해상도 3시간**: 매칭 결과 시각이 출력에 표시됨
- **Windy API 무료 한도**: 단기 스레드가 10분마다 API를 호출하므로 하루 약 144회.
  무료 한도 초과 여부 실사용 중 확인 필요
- **민감 정보**: `.env`는 반드시 `.gitignore`에 포함
