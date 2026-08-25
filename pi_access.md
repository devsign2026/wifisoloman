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
