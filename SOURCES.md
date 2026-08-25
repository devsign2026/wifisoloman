# 외부 자료 및 출처 구분

> 이 프로젝트에서 **직접 검증한 것**과 **외부에서 받아온 것**을 구분해 기록한다.
> 학술적으로 인용하실 때 반드시 원문을 직접 확인하십시오.

---

## 1. 코드에 실제로 쓰인 외부 소프트웨어

| 항목 | 출처 | 용도 |
|---|---|---|
| Nexmon CSI 펌웨어 | [nexmonster/nexmon_csi_bin](https://github.com/nexmonster/nexmon_csi_bin) | Pi WiFi 칩에서 CSI 추출 |
| 원본 Nexmon CSI | [seemoo-lab/nexmon_csi](https://github.com/seemoo-lab/nexmon_csi) | 위 바이너리의 원본 |
| CSIKit | [Gi-z/CSIKit](https://github.com/Gi-z/CSIKit) | pcap 파싱 (오프라인 분석) |
| numpy / scipy / matplotlib | — | 신호처리·시각화 |

`csi_stream.py`(실시간 파서)는 CSIKit의 `NEXBeamformReader` 동작을 참고해
같은 결과가 나오도록 직접 작성했다. 동일 파일에서 타임스탬프·CSI 값이 일치함을
확인했다 (history.md 23번).

---

## 2. 참고했으나 **원문을 확인하지 않은** 자료 ⚠️

2026-08-26 세션에서 사용자가 붙여넣은 문헌 요약을 참고했다.
그 요약은 별도 검색 도구의 결과물이며, **이 저장소 작업 과정에서 원문·DOI·수치를
직접 확인하지 않았다.** 아래 서술은 그 요약에 근거한 것이므로, 인용 전 반드시 검증할 것.

요약에 등장한 연구 (미검증):

- Sleep Apnea Monitoring System Based on Commodity WiFi Devices (2021)
- Tracking Vital Signs During Sleep Leveraging Off-the-shelf WiFi
- PhaseBeat: Exploiting CSI Phase Data for Vital Sign Monitoring
- FarSense: Pushing the Range Limit of WiFi-based Respiration Sensing
- SMARS: Sleep Monitoring via Ambient Radio Signals
- ResBeat: Resilient Breathing Beats Monitoring
- Vital-Radio (MIT, CHI 2015) — 맞춤형 FMCW 장비 사용

### 이 자료가 실제로 영향을 준 결정 (2곳)

1. **배치를 1m로 좁힘** — Sleep Apnea 논문의 송수신기 90cm 조건을 참고
2. **안테나 개수 한계 판단** — FarSense가 두 안테나 CSI 비율을, PhaseBeat가 안테나
   간 위상차를 쓴다는 서술에 근거해, 우리 1x1 구성에서 그 기법을 쓸 수 없다고 판단

이 두 가지 외에는 논문에서 알고리즘이나 수치를 가져오지 않았다.

---

## 3. 이 저장소에서 직접 측정·검증한 것

문헌이 아니라 **우리 데이터로 확인한 사실**이다. 재현 절차는 history.md 참조.

- 밴드패스 필터의 수치 불안정 (`b,a` 형태 → 극점 반경 1.0039, 발산). SOS로 교체
- 측정 경로가 공유기→파이가 아니라 **맥북→파이** (CSI 프레임 전량의 발신 MAC 확인)
- 진폭으로는 재실이 안 갈리고(p=0.900) 위상으로는 갈림(p<0.001, 겹침 0/13)
- Pi 4B BCM43455c0은 **1x1** (CSI shape `(256,1,1)`, core 0 하나)
- 호흡 중/숨참기 구분 실패 (12창 중 10창 겹침, 주파수 증거 없음)
- 실측 샘플링레이트 37~142Hz (ping 간격에 따라 변동)

---

## 4. 위상 정제 기법에 대하여

`sanitize_phase()` 는 패킷마다 서브캐리어축의 선형 위상 램프(CFO/SFO/패킷 검출
지연에서 기인)를 제거한다. 이는 CSI 문헌에서 널리 쓰이는 표준 전처리로 알려져
있으나, **특정 논문을 확인하고 옮긴 것이 아니라 일반적으로 알려진 방법을
구현한 것이다.** 정확한 출처 표기가 필요하면 원 논문을 직접 찾아 확인할 것.
