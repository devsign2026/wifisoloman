# config.sh 템플릿. 복사해서 실제 값을 채울 것:
#   cp config.example.sh config.sh
# config.sh 는 .gitignore 에 있어 커밋되지 않는다.

export PI_HOST="raspberrypi.local"     # mDNS 호스트명. IP 하드코딩 금지
export PI_USER="pi"
# 파이 eth0 MAC — 공유기 DHCP 예약에 사용. `cat /sys/class/net/eth0/address`
export PI_ETH_MAC="xx:xx:xx:xx:xx:xx"
# DHCP 실패 시 폴백 주소 (/etc/dhcpcd.conf 의 static_fallback 과 일치시킬 것)
export PI_FALLBACK_IP="172.30.1.222"

export ROUTER_SSID="<실험용 5GHz SSID>"
export ROUTER_IP="192.168.0.1"
export CHANNEL="149/80"                # 채널/대역폭. DFS(52~144) 피할 것

# 트래픽 발생기로 쓸 기기의 MAC. 이 MAC이 보낸 패킷에서만 CSI를 뽑는다.
#   macOS: ifconfig en0 | grep ether
export TX_MAC="xx:xx:xx:xx:xx:xx"

export PING_INTERVAL="0.05"   # 트래픽 발생기 ping 간격. 캡처 간 비교하려면 고정할 것

# 아래 명령의 출력을 그대로 붙여넣을 것:
#   makecsiparams -c $CHANNEL -C 1 -N 1 -m $TX_MAC
export CSI_PARAMS="<makecsiparams 출력>"
