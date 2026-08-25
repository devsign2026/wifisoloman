#!/usr/bin/env python3
"""
Nexmon CSI pcap 스트림 파서.

CSIKit은 파일 단위로만 읽어서 실시간에 못 쓴다. 이 모듈은 tcpdump의
`-U -w -` 출력(패킷 단위로 flush되는 pcap 스트림)을 그대로 받아
프레임이 도착하는 즉시 하나씩 내놓는다.

포맷 (BCM43455c0, CSIKit NEXBeamformReader와 동일하게 맞춤):
  pcap 글로벌 헤더 24바이트
  레코드마다: ts_sec(4) ts_usec(4) incl_len(4) orig_len(4) + 패킷 데이터
  패킷 데이터: Ethernet(14) + IP(20) + UDP(8) + nexmon 헤더(18) = 60바이트 건너뜀
  그 뒤 int16 쌍 (실수, 허수) 이 서브캐리어 순으로
"""
import struct

import numpy as np

PCAP_GLOBAL_LEN = 24
RECORD_HEADER_LEN = 16
CSI_DATA_OFFSET = 60          # Ethernet + IP + UDP + nexmon 헤더
NEXMON_HEADER_OFFSET = 42     # Ethernet + IP + UDP


def _read_exactly(stream, n):
    """스트림에서 정확히 n바이트를 읽는다. EOF면 None."""
    buf = b""
    while len(buf) < n:
        chunk = stream.read(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def iter_frames(stream, expect_subcarriers=256):
    """
    pcap 스트림 -> (timestamp, csi[complex64]) 제너레이터.

    글로벌 헤더의 magic으로 엔디안과 나노초 여부를 판별한다.
    """
    header = _read_exactly(stream, PCAP_GLOBAL_LEN)
    if header is None:
        return
    magic = header[:4]
    if magic == b"\xd4\xc3\xb2\xa1":
        endian, nano = "<", False
    elif magic == b"\xa1\xb2\xc3\xd4":
        endian, nano = ">", False
    elif magic == b"\x4d\x3c\xb2\xa1":
        endian, nano = "<", True
    elif magic == b"\xa1\xb2\x3c\x4d":
        endian, nano = ">", True
    else:
        raise ValueError(f"pcap 매직이 아님: {magic!r}")

    rec_fmt = endian + "IIII"
    divisor = 1e9 if nano else 1e6

    while True:
        rec = _read_exactly(stream, RECORD_HEADER_LEN)
        if rec is None:
            return
        ts_sec, ts_frac, incl_len, _ = struct.unpack(rec_fmt, rec)
        payload = _read_exactly(stream, incl_len)
        if payload is None:
            return
        if incl_len <= CSI_DATA_OFFSET:
            continue

        raw = np.frombuffer(payload, dtype=np.int16, offset=CSI_DATA_OFFSET,
                            count=(incl_len - CSI_DATA_OFFSET) // 2)
        if len(raw) < 2 * expect_subcarriers:
            continue
        pairs = raw[: 2 * expect_subcarriers].reshape(-1, 2)
        csi = pairs.astype(np.float32).view(np.complex64).ravel()
        yield ts_sec + ts_frac / divisor, csi


def frames_to_arrays(frames):
    """[(t, csi), ...] -> (timestamps[N], csi[N, subcarriers])"""
    if not frames:
        return np.empty(0), np.empty((0, 0), dtype=np.complex64)
    t = np.array([f[0] for f in frames], dtype=np.float64)
    c = np.stack([f[1] for f in frames])
    return t, c
