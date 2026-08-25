# 파이 접속 정보

> 실제 호스트명·계정은 `config.sh` 에 있음 (git 미포함).
> `source config.sh` 후 아래 명령의 변수가 채워짐.

| 항목 | 값 |
|---|---|
| 호스트 | **`$PI_HOST`** ← 항상 이걸 쓸 것 (IP 하드코딩 금지) |
| 계정 | `$PI_USER` (config.sh) |

```bash
ssh $PI_USER@$PI_HOST
```

## ⚠️ IP를 직접 쓰지 말 것

파이 IP는 DHCP라 재부팅·공유기 재시작 때마다 바뀝니다.
(실제로 `172.30.1.26` → `172.30.1.29` 로 바뀐 적 있음)

`$PI_HOST`은 mDNS라서 파이가 스스로 현재 IP를 알려줍니다.
**IP가 바뀌어도 그대로 접속되므로 문서를 고칠 필요가 없습니다.**

현재 IP가 궁금하면:
```bash
ssh $PI_USER@$PI_HOST 'hostname -I'
```

## 주소 확보 3중 안전장치

1. **`$PI_HOST` (mDNS)** — 평소 이걸 쓴다. IP가 바뀌어도 알아서 찾는다
2. **DHCP 폴백** — DHCP 자체가 실패하면 `$PI_FALLBACK_IP` 로 떨어진다 (2026-08-26 설정, 실제 값은 `config.sh`)
   - `/etc/dhcpcd.conf` 의 `profile static_fallback` 참조
   - 평소 동작에는 영향 없음. DHCP가 되면 DHCP 주소를 쓴다
   - 되돌리기: `sudo cp /etc/dhcpcd.conf.bak.* /etc/dhcpcd.conf && sudo reboot`
3. **공유기 DHCP 예약** (권장, 미설정) — 공유기 관리페이지에서
   eth0 MAC (`config.sh` 의 `$PI_ETH_MAC`) 에 고정 IP를 묶어두면 가장 안전하다.
   파이 설정을 건드리지 않으므로 다른 네트워크에 꽂아도 문제가 없다

> ⚠️ **파이에 고정 IP를 직접 박지 말 것.** 다른 대역의 공유기(예: ipTIME 192.168.0.x)에
> 꽂으면 통신이 안 되고, 모니터·키보드 없이는 되돌릴 수 없다.

### raspberrypi.local이 안 될 때만 (드묾)

mDNS를 막는 네트워크에서는 IP를 직접 찾아야 함:
```bash
# 같은 대역 스캔 (172.30.1.x 인 경우)
arp -a | grep -i b8:27:eb   # 라즈베리파이 MAC 접두사
arp -a | grep -i dc:a6:32   # Pi 4 계열 접두사
```
또는 랜선이 꽂힌 공유기 관리 페이지의 DHCP 접속 목록에서 확인.

## SSH 키 등록 (등록 완료됨)

비밀번호 없이 `ssh`/`scp`가 동작하도록 이미 등록해둠.

새 맥에서 다시 해야 한다면 — Claude Code 세션은 pseudo-terminal이 없어
비밀번호 대화형 입력이 안 되므로 **macOS 터미널 앱에서 직접** 실행:

```bash
ssh-copy-id $PI_USER@$PI_HOST
```

---
참고: [RUN.md](./RUN.md) 캡처 실행 순서 · [nexmon_csi_setup.md](./nexmon_csi_setup.md) 2-4절
