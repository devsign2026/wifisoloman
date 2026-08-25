# 캡처 세션 실행 순서 (매번 이대로)

> 셋업 원리·트러블슈팅은 [nexmon_csi_setup.md](./nexmon_csi_setup.md), 진행 기록은 [history.md](./history.md).
> 이 문서는 **이미 셋업이 끝난 상태에서 캡처 한 번 돌리는 절차**만 담음.

등장인물 3명:
- **파이** — CSI 수신(센서). SSH로 조종.
- **남는 맥북** — ping 쏘는 역할. 이게 없으면 데이터 0개.
- **작업 맥북(이거)** — 분석. scp로 파일 받아옴.

---

## 0. 설정 불러오기 ⭐ (터미널 열 때마다)

SSID·MAC 같은 실제 값은 `config.sh` 에 있음 (git 미포함).
**이걸 먼저 실행해야 아래 명령의 `$PI_HOST` 등이 채워짐.**

```bash
cd ~/Desktop/프로젝트/wifi
source config.sh
```

> 처음이라 `config.sh` 가 없으면: `cp config.example.sh config.sh` 후 값 채우기.

파이가 살아있는지 확인 (IP는 DHCP라 바뀌므로 호스트명 사용):

```bash
ping -c 2 $PI_HOST
ssh $PI_USER@$PI_HOST 'hostname -I'
```

---

## 1. 파이 CSI 설정 주입 ⭐ (재부팅했으면 반드시)

재부팅하면 날아감. 안 하고 캡처하면 **패킷 0개**.

```bash
ssh $PI_USER@$PI_HOST '
sudo ifconfig wlan0 up
sudo nexutil -Iwlan0 -s500 -b -l34 -v$CSI_PARAMS
sudo iw dev wlan0 interface add mon0 type monitor 2>/dev/null
sudo ifconfig mon0 up
sudo nexutil -k
'
```

**`chanspec: 0xe09b, 149/80` 이 나와야 정상.**
`chanspec: 0x1007, 7` 같은 게 나오면 주입 실패 → 다시 실행.

---

## 2. 남는 맥북 준비

1. WiFi를 **`$ROUTER_SSID`** 에 연결
2. 시스템 설정 → Wi-Fi → $ROUTER_SSID "상세..." → **프라이빗 Wi-Fi 주소 = 끔**
   (안 끄면 MAC이 바뀌어서 위 필터 `$TX_MAC`가 안 맞아 패킷 0개)
3. MAC 확인:
   ```bash
   ifconfig en0 | grep ether     # → $TX_MAC 여야 함
   ```
   > 다르면 `makecsiparams -c 149/80 -C 1 -N 1 -m <새MAC>` 로 파라미터 새로 만들어 1단계 재실행.

---

## 3. 배치 (실험 재현성의 핵심)

```
   [공유기]  ←── 1.5~3m ──→  [파이]
        └──── 사이에 사람 앉기 ────┘

   [남는 맥북] ← 구석에 방치, ping만 쏨
```

- 공유기·파이 높이 = **앉은 자세 가슴 높이 (90~110cm)**
- **선풍기/에어컨 OFF** ← 호흡 감지 최대의 적
- 방에 다른 사람/반려동물 없을 것
- 공유기·파이 위치를 **테이프로 고정** (캡처 간 비교하려면 위치가 같아야 함)

---

## 4. ping 시작 (남는 맥북)

```bash
sudo ping -i 0.01 192.168.0.1
```

- 초당 100패킷 → CSI 샘플링 ~100Hz
- **캡처 내내 멈추지 말 것.** 모든 캡처 끝날 때까지 켜둠
- 패킷 0개 증상이면 Ctrl+C 후 2~3번 재시작 (알려진 현상)

---

## 5. 사전 점검 캡처 (20초, 강력 권장)

본 실험 전에 패킷이 실제로 잡히는지 먼저 확인.

```bash
ssh $PI_USER@$PI_HOST 'sudo timeout 25 tcpdump -i wlan0 dst port 5500 -w ~/precheck.pcap -c 200'
```

`200 packets captured / 0 packets dropped` 가 몇 초 안에 뜨면 OK.
안 뜨고 멈춰 있으면 → 2번(맥북 WiFi/MAC) 또는 1번(chanspec) 재확인.

---

## 6. 본 캡처

각 캡처 사이에 자세 고정하고, 메트로놈 박자대로 호흡.
6000패킷 ≈ 60~80초.

> ⚠️ **패킷 수(`-c`)가 아니라 시간(`timeout`)으로 찍을 것.**
> 샘플링레이트가 트래픽 상황에 따라 77~127Hz로 변합니다. `-c 6000`으로 찍으면
> 어떤 날은 85초, 어떤 날은 47초가 되어 캡처끼리 비교가 안 됩니다.
> (2026-08-25에 127Hz가 나와서 `-c 3000`이 40초가 아닌 22초로 끝난 사례 있음)

```bash
# ② 12 BPM (0.2Hz) — 90초
ssh $PI_USER@$PI_HOST 'sudo timeout 90 tcpdump -i wlan0 dst port 5500 -w ~/breath_12bpm_$(date +%Y%m%d).pcap'

# ③ 15 BPM (0.25Hz)
ssh $PI_USER@$PI_HOST 'sudo timeout 90 tcpdump -i wlan0 dst port 5500 -w ~/breath_15bpm_$(date +%Y%m%d).pcap'

# ④ 20 BPM (0.33Hz)
ssh $PI_USER@$PI_HOST 'sudo timeout 90 tcpdump -i wlan0 dst port 5500 -w ~/breath_20bpm_$(date +%Y%m%d).pcap'

# ① 기준선 — 방에서 나간 상태 (마지막에)
ssh $PI_USER@$PI_HOST 'sudo timeout 90 tcpdump -i wlan0 dst port 5500 -w ~/baseline_empty_$(date +%Y%m%d).pcap'
```

**90초를 쓰는 이유:** 가장 느린 12 BPM에서도 호흡 18회가 들어가야 주파수 분해능이 확보됩니다.
호흡 캡처와 기준선을 **같은 길이로** 찍어야 스펙트럼 비교가 성립합니다.

**호흡 요령 (1차 실패 교훈):**
- 메트로놈은 **스피커로 소리만** 듣기. 화면 보려고 폰 들면 그 움직임이 호흡 신호를 덮어버림
- 캡처 시작 후 손·상체 움직이지 말 것. 자세 바꾸면 그 구간은 버리는 데이터
- 카운트다운 후 시작하고, 캡처 끝날 때까지 가만히

---

## 7. 파일 받아서 분석

```bash
cd /Users/homin/Desktop/프로젝트/wifi
scp $PI_USER@$PI_HOST:~/*.pcap data/
# 받은 뒤 data/README.md 대장에 실제 환경 조건을 기록할 것

### 7-1. 먼저 진단 — "호흡 신호가 있기는 한가?" ⭐

`csi_pipeline.py`는 신호가 없어도 BPM 숫자를 뱉습니다. 그 숫자부터 보면
잡음을 호흡으로 오독합니다 (1차 실패가 정확히 이 함정). **진단을 먼저 돌리세요.**

```bash
python3 csi_diagnose.py data/breath_12bpm_<날짜>.pcap --expect 12
python3 csi_diagnose.py data/breath_15bpm_<날짜>.pcap --expect 15
python3 csi_diagnose.py data/breath_20bpm_<날짜>.pcap --expect 20
python3 csi_diagnose.py data/baseline_empty_<날짜>.pcap    # 기준선은 --expect 없이
```

- **❌ 판정이 하나라도 뜨면 → 아래 7-2로 넘어가지 말 것.** 환경 고치고 재캡처.
- 피크가 `0.10Hz`에 몰린다는 경고 → 캡처 중 자세 변화/환경 변동. 더 가만히 있어야 함.
- baseline은 호흡 캡처와 **분포가 달라야** 정상. 똑같으면 호흡을 못 잡은 것.

### 7-2. ✅ 가 나왔을 때만 — BPM 추정

```bash
python3 csi_pipeline.py data/breath_12bpm_<날짜>.pcap --plot data/breath_12bpm_<날짜>_plot.png
python3 csi_pipeline.py data/breath_15bpm_<날짜>.pcap --plot data/breath_15bpm_<날짜>_plot.png
python3 csi_pipeline.py data/breath_20bpm_<날짜>.pcap --plot data/breath_20bpm_<날짜>_plot.png
python3 csi_pipeline.py data/baseline_empty_<날짜>.pcap --plot data/baseline_empty_<날짜>_plot.png
```

**성공 기준:**
> 12 / 15 / 20 캡처의 FFT 피크가 각각 **0.2 / 0.25 / 0.33Hz 근처**에서
> **순서대로 커져야** 함. 한 번 맞은 건 우연일 수 있음.

한 번이라도 순서가 깨지면 → `history.md`에 결과 기록하고 원인 분석.

---

## 8. 결과 푸시

캡처와 분석이 끝나면 `data/README.md` 대장에 환경 조건을 적고 푸시.

```bash
git add -A && git commit -m "캡처 추가: <설명>" && git push
# 원격: https://github.com/devsign2026/wifisoloman
```

> `config.sh` 가 `git status` 에 보이면 커밋하지 말 것 (실제 SSID/MAC 포함).

---

## 빠른 체크리스트

- [ ] 파이 켜짐, `ssh $PI_USER@$PI_HOST` 됨
- [ ] `sudo nexutil -k` → `0xe09b, 149/80`
- [ ] 남는 맥북이 `$ROUTER_SSID`에 붙음, 프라이빗 WiFi 주소 끔, MAC 일치
- [ ] 공유기↔파이 1.5~3m, 가슴 높이, 사이에 사람
- [ ] **선풍기/에어컨 OFF**
- [ ] 남는 맥북에서 `sudo ping -i 0.01 192.168.0.1` 돌아가는 중
- [ ] precheck 200패킷 성공
- [ ] 메트로놈 스피커 재생, 폰 내려놓음
- [ ] **방에 나 말고 아무도 없음** ← 1차 실패의 유력 원인
