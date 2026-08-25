# Raspberry Pi 4B — Nexmon CSI 셋업 가이드

> WiFi CSI(Channel State Information)로 호흡/움직임을 감지하기 위한 수집 환경 구축.
> **이 문서는 셋업 전용입니다.** 처음부터 다시 할 때 그대로 따라하면 됩니다.
>
> | 문서 | 역할 |
> |---|---|
> | **이 문서** | OS 설치 ~ Nexmon 설치 (한 번만) |
> | [RUN.md](./RUN.md) | 캡처 세션 실행 절차 (매번) |
> | [data/README.md](./data/README.md) | 캡처 파일별 실제 환경 조건 |
> | [history.md](./history.md) | 작업 기록 · 분석 결과 |

---

## 0. 확정된 환경

| 항목 | 값 |
|---|---|
| 하드웨어 | Raspberry Pi 4B (WiFi 칩: **BCM43455c0**) |
| OS | Raspberry Pi OS **Lite, Bullseye, 32bit(armhf)** |
| 이미지 | `2022-01-28-raspios-bullseye-armhf-lite` |
| **커널** | **`5.10.92-v7l+`** ← 절대 변경 금지 |
| 파이 접속 주소 | `$PI_HOST` (IP는 DHCP라 바뀜 → 호스트명 사용) |
| 실험용 공유기 | ipTIME, SSID `$ROUTER_SSID` |
| 채널/대역폭 | **149 / 80MHz** (5745MHz) |
| 트래픽 발생기 | 남는 맥북, MAC `$TX_MAC` |
| 공유기 IP | `192.168.0.1` |

---

## 🚨 절대 금지 명령어

```bash
sudo apt upgrade        # ❌ 커널 변경 → 프로젝트 사망
sudo apt full-upgrade   # ❌
sudo apt dist-upgrade   # ❌
sudo rpi-update         # ❌❌
```

Nexmon CSI는 커널 **5.10.92**에 정확히 묶여 있습니다.
커널이 바뀌면 펌웨어 패치가 동작하지 않고 **SD카드를 다시 구워야 합니다.**

- `apt update` (목록 갱신) → ✅ 허용
- `apt install <특정패키지>` → ✅ 허용

---

## 1. 네트워크 구조 (이해 필수)

```
[학교/집 공유기]  ──랜선──→  [파이 eth0]
   (인터넷 O)                  인터넷 + SSH 전용

[ipTIME "$ROUTER_SSID"]  ~~~전파~~~>  [파이 wlan0]
   (인터넷 불필요, 신호만)          CSI 센서 전용
        ↕ ping 홍수
   [남는 맥북]
```

**핵심:**
- 파이 **WiFi는 인터넷을 못 씁니다.** 센서로 징발되기 때문.
- 그래서 **랜선이 필수**입니다. SSH가 유선으로 들어와야 합니다.
- 랜선은 **맥북이 아니라 인터넷 되는 공유기의 LAN 포트**에 꽂습니다.
- CSI는 **패킷이 날아갈 때만** 추출됩니다. 그래서 ping으로 트래픽을 강제 유발합니다.

---

## 2. OS 설치

### 2-1. 이미지 다운로드
```
https://downloads.raspberrypi.org/raspios_lite_armhf/images/raspios_lite_armhf-2022-01-28/
```
→ `2022-01-28-raspios-bullseye-armhf-lite.zip`

### 2-2. 굽기
- Raspberry Pi Imager → **`Use custom`** 으로 위 파일 선택
- ⚠️ 목록에서 "최신 OS" 고르면 안 됨
- ⚠️ 구버전 이미지는 Imager의 ⚙️ 사전설정이 **비활성화됨** → 수동 SSH 활성화 필요

### 2-3. SSH 수동 활성화
SD카드의 `boot` 파티션에 확장자 없는 빈 파일 생성:
```bash
touch /Volumes/boot/ssh      # macOS
# 마운트명이 bootfs일 수도 있음: ls /Volumes/
```

### 2-4. 접속
```bash
ssh $PI_USER@$PI_HOST
# 이 이미지의 기본 계정/비밀번호는 라즈베리파이 공식 문서 참조.
# (기본 pi 계정은 2022-04-04 릴리스부터 제거됨. 1월 이미지엔 살아있음)
# ⚠️ 설치 직후 반드시 passwd 로 비밀번호를 변경할 것.
```

---

## 3. 부팅 직후 (순서 엄수)

```bash
# ① 커널 확인 — 다르면 여기서 중단
uname -r
# → 5.10.92-v7l+

# ② 커널 잠금 (다른 어떤 명령보다 먼저!)
sudo apt-mark hold raspberrypi-kernel raspberrypi-bootloader raspberrypi-kernel-headers
sudo apt-mark showhold

# ③ 기본 설정
sudo raspi-config
#   → Localisation Options → WLAN Country → KR   (필수)
#   → Advanced Options → Expand Filesystem
#   ⚠️ "Update" 항목 절대 누르지 말 것

sudo reboot
```

재부팅 후 확인:
```bash
uname -r          # 5.10.92-v7l+ 유지
rfkill list       # wlan: Soft blocked: no
# blocked면: sudo rfkill unblock wifi
```

---

## 4. 유선 인터넷 확인

```bash
ip a show eth0
ping -c 3 8.8.8.8
```

| 증상 | 원인 |
|---|---|
| IP가 `169.254.x.x` | DHCP 서버 없음 → **랜선이 맥북에 직결됐거나 엉뚱한 곳에 꽂힘** |
| IP가 `192.168.x.x` / `172.x.x.x` | 정상 |

**랜선은 인터넷 되는 공유기의 LAN 포트(WAN 아님)에 꽂을 것.**

---

## 5. 공유기 설정 (ipTIME)

`192.168.0.1` → `admin`/`admin`

| 항목 | 설정 |
|---|---|
| SSID | `$ROUTER_SSID` |
| 채널 | **고정 149** (자동 ❌, DFS 채널 52~144 피할 것) |
| 대역폭 | **80MHz** |
| 2.4GHz | **끄기** (기기가 멋대로 붙는 것 방지) |
| 밴드 스티어링 | **끄기** |
| 채널 자동변경 | **끄기** |

파이에서 확인:
```bash
sudo iw dev wlan0 scan | grep -E "SSID:|freq:"
# → SSID: $ROUTER_SSID / freq: 5745  (= 채널 149)
```

**주파수 ↔ 채널 대응**
| freq | 채널 |
|---|---|
| 5180 | 36 |
| 5745 | **149** |
| 5785 | 157 |
| 2437 | 6 |

---

## 6. 트래픽 발생기 (남는 맥북)

1. `$ROUTER_SSID` 에 연결
2. **프라이빗 Wi-Fi 주소 끄기**
   - 시스템 설정 → Wi-Fi → 네트워크 "상세..." → 프라이빗 Wi-Fi 주소 **끔**
   - ⚠️ 안 끄면 재연결마다 MAC이 바뀌어 필터가 깨짐
3. MAC 확인
   ```bash
   ifconfig en0 | grep ether
   # → $TX_MAC
   ```

---

## 7. Nexmon CSI 설치

### 7-1. 저장소 가져오기

인터넷이 막히면 **맥북에서 clone → scp**:
```bash
# 맥북
git clone https://github.com/nexmonster/nexmon_csi_bin.git
scp -r nexmon_csi_bin $PI_USER@$PI_HOST:~/
```

### 7-2. 설치
```bash
cd ~/nexmon_csi_bin
sudo bash install.sh
sudo reboot
```

스크립트가 하는 일:
- `5.10.92-v7l+.tar.xz` 다운로드 (GitHub = HTTPS라 학교망도 통과)
- 패치된 `brcmfmac.ko` + `brcmfmac43455-sdio.bin` 설치
- `nexutil`, `makecsiparams` 설치
- `fdisk`로 루트 파티션 확장 (정상 동작, 데이터 안 날아감)

### 7-3. 검증 ⭐
```bash
uname -r
# → 5.10.92-v7l+

dmesg | grep brcmfmac | grep -i version
# → version 7.45.189 (nexmon.org/csi: c037-1)
#                     ^^^^^^^^^^^ 이게 보여야 성공
```

**`nexmon.org` 문자열이 없으면 설치 실패입니다.**

---

## 8. tcpdump 설치 (학교망 우회)

apt가 막히면 맥북에서 `.deb` 받아 넘기기:

**브라우저로** 아래 열어서 `armhf.deb` 다운로드:
```
https://deb.debian.org/debian/pool/main/t/tcpdump/
https://deb.debian.org/debian/pool/main/libp/libpcap/
```

```bash
# 맥북
scp ~/Downloads/*.deb $PI_USER@$PI_HOST:~/

# 파이
sudo dpkg -i libpcap0.8_*.deb
sudo dpkg -i tcpdump_*.deb
tcpdump --version
```

> ⚠️ 학교망 함정: HTTP는 리다이렉트/차단으로 깨지고, **HTTPS는 통과**함.
> `curl`은 `-L` (리다이렉트 추종) 필수. 받은 파일이 몇 KB면 HTML(차단/404) 페이지임.

---

## 9. CSI 캡처 ⭐

### 9-1. 파라미터 생성
```bash
makecsiparams -c 149/80 -C 1 -N 1 -m $TX_MAC
# → $CSI_PARAMS
```
- `-c 149/80` : 채널/대역폭
- `-C 1 -N 1` : 코어/스트림 (파이는 안테나 1개 → 그대로 둘 것)
- `-m` : **이 MAC이 보낸 패킷에서만** CSI 추출 (필터)

### 9-2. 인터페이스 설정
```bash
sudo ifconfig wlan0 up

sudo nexutil -Iwlan0 -s500 -b -l34 -v$CSI_PARAMS
# ⚠️ -v 뒤에 공백 없이 붙일 것

sudo iw dev wlan0 interface add mon0 type monitor
sudo ifconfig mon0 up
# "Operation not supported (-95)" → mon0이 이미 있는 것. 무시 가능

# 채널 확인
sudo nexutil -k
# → chanspec: 0xe09b, 149/80
```

### 9-3. 트래픽 유발 (남는 맥북)
```bash
sudo ping -i 0.01 192.168.0.1
```
- **멈추지 말고 계속 돌려둘 것**
- 실측 CSI 샘플링레이트는 **77~127Hz로 변동**함 (트래픽 상황에 따라 다름).
  호흡(0.2~0.5Hz) 감지에는 어느 쪽이든 충분하나, 캡처 길이를 패킷 수로 정하면 안 되는 이유가 됨.

### 9-4. 캡처 (파이)
```bash
sudo tcpdump -i wlan0 dst port 5500 -vv -w /home/pi/csi_test.pcap -c 1000
```

> ⚠️ **`mon0`이 아니라 `wlan0`** 에서 캡처. Pi 3B+/4B는 이렇게 해야 함 (Nexmon 공식 문서 명시)

**성공 출력:**
```
1000 packets captured
0 packets dropped by kernel
```

---

## 10. 재부팅 후 재시작 절차

재부팅하면 nexutil 설정이 날아갑니다. **캡처 전 매번 재주입 필요.**

→ 절차는 **[RUN.md](./RUN.md) 1단계** 참조 (이 문서에 중복해 두지 않음).

---

## 11. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| 패킷 0개 | 맥북 ping을 Ctrl+C 후 **2~3번 재시작**. 알려진 현상 |
| 패킷 0개 | 남는 맥북이 `$ROUTER_SSID`에 안 붙어 있음 |
| 패킷 0개 | MAC 필터 빼고 테스트: `makecsiparams -c 149/80 -C 1 -N 1` (`-m` 생략) |
| `nexutil -k`가 다른 채널 | 파라미터 재주입 |
| `dmesg`에 nexmon 없음 | 펌웨어 설치 실패 → install.sh 재실행 |
| apt `NOSPLIT` 에러 | 학교망 HTTP 차단. HTTPS 미러 쓰거나 .deb 수동 설치 |
| IP가 `169.254.x.x` | 랜선이 공유기에 안 꽂힘 |

---

## 12. CSI 데이터 형식 (파싱용 참고)

- UDP **포트 5500** 으로 전송됨
- 각 CSI 샘플 = **4바이트** (Int16 실수부 + Int16 허수부, 교차 배치)
- 서브캐리어 개수 = **대역폭 × 3.2**
  - 80MHz → **256개**
  - 40MHz → 128개
  - 20MHz → 64개
- 패킷 1개 = 서브캐리어 256개 × 4바이트 = **1024바이트** + 헤더

**파서 추천:**
- [CSIKit](https://github.com/Gi-z/CSIKit) — 여러 포맷 지원
- [csi-explorer](https://github.com/zeroby0/csi-explorer) — Pi 전용, 속도 최적화

---

## 13. 실험 실행

> 🚨 **측정 경로는 공유기→파이가 아니라 맥북→파이입니다.**
> `makecsiparams -m` 필터가 트래픽 발생기(맥북) MAC으로 걸려 있어, 파이는
> **그 MAC이 송신한** 프레임에서만 CSI를 뽑습니다. 실측 확인됨 (CSI 프레임 전량이
> 맥북 발신). **공유기는 ping 목적지일 뿐 측정 경로에 없습니다.**
>
> ```
> [맥북] ~~~측정되는 경로~~~> [파이]
>     └──── 여기에 사람 ────┘
> [공유기] ← ping 목적지. 위치 무관
> ```
>
> 이 문서의 예전 배치도는 "공유기↔파이 사이에 사람, 맥북은 구석에 방치"로
> 잘못 그려져 있었습니다. 2026-08-26 정정.

배치·캡처·분석 절차는 전부 **[RUN.md](./RUN.md)** 로 분리했습니다.

> ⚠️ 예전에 이 자리에 있던 `tcpdump ... -c 3000` 형태의 캡처 명령은 **폐기됨.**
> 샘플링레이트가 77~127Hz로 변동해 패킷 수로 찍으면 캡처마다 길이가 달라집니다.
> 반드시 시간 기준(`timeout 90`)으로 찍을 것 — 자세한 이유는 RUN.md 6장.

캡처된 파일의 실제 환경 조건은 **[data/README.md](./data/README.md)** 대장에 기록합니다.

---

## 14. 알려진 한계 (프로젝트 설계 시 참고)

- **대상이 정지 상태여야 함.** 걸어다니면 호흡 신호는 몸통 움직임에 완전히 묻힘
  → 실용적으론 "수면 중 / 앉은 자세" 모니터링에 적합
- **한 명만.** 다중 인원 호흡 분리는 안테나 배열이 필요
- **환경 의존성이 큼.** 가구 배치만 바꿔도 재보정 필요
- **낙상 감지는 데이터 확보가 근본 난제.** 연출된 낙상 ≠ 실제 낙상
  → "낙상 이벤트 감지"보다 **"이상 정적 상태 감지"** 로 문제를 재정의하는 것을 권장
- ⚠️ **이 시스템을 유일한 안전망으로 쓰면 안 됨.** 응급벨 등과 병행할 것

---

## 참고 링크

- [nexmon_csi_bin](https://github.com/nexmonster/nexmon_csi_bin) — 사전컴파일 바이너리
- [nexmon_csi (pi-5.10.92)](https://github.com/nexmonster/nexmon_csi/tree/pi-5.10.92) — Usage 문서
- [seemoo-lab/nexmon_csi](https://github.com/seemoo-lab/nexmon_csi) — 원본
- [CSIKit](https://github.com/Gi-z/CSIKit) — 파서
