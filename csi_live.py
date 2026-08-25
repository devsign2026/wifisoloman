#!/usr/bin/env python3
"""
CSI 실시간 모니터 — 파이에서 짧게 반복 캡처해 호흡 대역 위상 변동을 그린다.

왜 5초마다 갱신인가: 호흡은 0.2Hz(5초 주기)라 대역 에너지를 안정적으로 재려면
최소 30초 데이터가 필요하다. 그래서 30초 롤링 창을 5초마다 다시 계산한다.
초당 갱신되는 그래프는 원리상 불가능하다.

사용법:
    source config.sh && python3 csi_live.py
    python3 csi_live.py --threshold 0.78 --chunk 5 --window 30
"""
import argparse
import os
import subprocess
import sys
import tempfile
import time
from collections import deque

import numpy as np

from csi_pipeline import (load_phase, sanitize_phase, resample_uniform,
                          bandpass_filter)

CHUNK_REMOTE = "/tmp/csi_live_chunk.pcap"


def ssh_base(host, user, ctl):
    return ["ssh", "-o", "ControlMaster=auto", "-o", f"ControlPath={ctl}",
            "-o", "ControlPersist=60", "-o", "ConnectTimeout=8", f"{user}@{host}"]


def grab_chunk(host, user, ctl, seconds, local_path):
    """파이에서 seconds초 캡처해 로컬로 가져온다. 실패하면 None."""
    cmd = ssh_base(host, user, ctl) + [
        f"sudo timeout {seconds} tcpdump -i wlan0 dst port 5500 "
        f"-w {CHUNK_REMOTE} >/dev/null 2>&1; cat {CHUNK_REMOTE}"]
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=seconds + 20).stdout
    except subprocess.TimeoutExpired:
        return None
    if len(out) < 1000:
        return None
    with open(local_path, "wb") as f:
        f.write(out)
    return local_path


def band_signal(timestamps, phase, low, high):
    """정제 위상 -> 서브캐리어 결합 -> 밴드패스. (시간축, 파형, rms) 반환."""
    clean = sanitize_phase(phase)
    fs = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])

    _, first = resample_uniform(timestamps, clean[:, 0], fs)
    mat = np.empty((len(first), clean.shape[1]))
    for i in range(clean.shape[1]):
        _, mat[:, i] = resample_uniform(timestamps, clean[:, i], fs)

    filtered = np.apply_along_axis(
        lambda y: bandpass_filter(y, fs, low=low, high=high), 0, mat)
    edge = int(3 * fs)
    if filtered.shape[0] <= 2 * edge:
        return None, None, None
    trimmed = filtered[edge:-edge]

    rms = np.median(trimmed.std(axis=0))
    # 변동이 큰 서브캐리어 상위 20개를 부호 맞춰 평균 -> 보기 좋은 대표 파형
    top = np.argsort(trimmed.std(axis=0))[::-1][:20]
    seg = trimmed[:, top]
    ref = seg[:, 0]
    signs = np.sign([np.corrcoef(ref, seg[:, i])[0, 1] for i in range(seg.shape[1])])
    signs[signs == 0] = 1
    waveform = (seg * signs).mean(axis=1)
    t = np.arange(len(waveform)) / fs
    return t, waveform, rms


def main():
    ap = argparse.ArgumentParser(description="CSI 실시간 모니터")
    ap.add_argument("--host", default=os.environ.get("PI_HOST", "raspberrypi.local"))
    ap.add_argument("--user", default=os.environ.get("PI_USER", "pi"))
    # 2026-08-26 배치·ping -i 0.05 기준 30초 창 13개씩 실측:
    #   빈 방   0.510~0.750
    #   사람4명 0.765~1.206
    # 겹침 0이지만 간격이 2%뿐이라 여유가 빠듯하다.
    # ⚠️ 배치나 ping이 바뀌면 빈 방을 다시 찍어 재보정할 것.
    ap.add_argument("--threshold", type=float, default=0.76, help="재실 판정 임계값")
    ap.add_argument("--chunk", type=float, default=5, help="한 번에 캡처할 초")
    ap.add_argument("--window", type=float, default=30, help="분석 창 (초)")
    ap.add_argument("--low", type=float, default=0.15)
    ap.add_argument("--high", type=float, default=0.6)
    ap.add_argument("--history", type=int, default=60, help="추이 그래프에 남길 점 개수")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("MacOSX" if sys.platform == "darwin" else "TkAgg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "AppleGothic"
    plt.rcParams["axes.unicode_minus"] = False

    ctl = os.path.join(tempfile.gettempdir(), "csi_live_ssh_%r@%h:%p")
    tmp = os.path.join(tempfile.gettempdir(), "csi_live_chunk.pcap")

    fig, (ax_wave, ax_trend) = plt.subplots(2, 1, figsize=(11, 7))
    fig.canvas.manager.set_window_title("CSI 실시간 모니터")

    rms_hist = deque(maxlen=args.history)
    time_hist = deque(maxlen=args.history)

    # 롤링 버퍼: (timestamps, phase) 조각들
    chunks = deque()
    t0 = time.time()

    print(f"파이 {args.user}@{args.host} 에서 {args.chunk:.0f}초마다 캡처합니다.")
    print(f"{args.window:.0f}초가 모이면 판정이 시작됩니다. 창을 닫으면 종료.\n")

    plt.ion()
    plt.show(block=False)

    try:
        while plt.fignum_exists(fig.number):
            got = grab_chunk(args.host, args.user, ctl, args.chunk, tmp)
            if got is None:
                print("[경고] 캡처 실패 — ping이 돌고 있는지 확인하세요")
                plt.pause(1.0)
                continue
            try:
                ts, ph = load_phase(got)
            except Exception as e:
                print(f"[경고] 파싱 실패: {e}")
                plt.pause(0.5)
                continue

            chunks.append((ts, ph))
            span = chunks[-1][0][-1] - chunks[0][0][0]
            while span > args.window and len(chunks) > 1:
                chunks.popleft()
                span = chunks[-1][0][-1] - chunks[0][0][0]

            all_ts = np.concatenate([c[0] for c in chunks])
            all_ph = np.concatenate([c[1] for c in chunks])
            order = np.argsort(all_ts)
            all_ts, all_ph = all_ts[order], all_ph[order]

            if all_ts[-1] - all_ts[0] < max(12, 1.0 / args.low * 2):
                elapsed = all_ts[-1] - all_ts[0]
                print(f"  버퍼 채우는 중... {elapsed:.0f}s / {args.window:.0f}s")
                plt.pause(0.1)
                continue

            t, wave, rms = band_signal(all_ts, all_ph, args.low, args.high)
            if wave is None:
                plt.pause(0.1)
                continue

            rms_hist.append(rms)
            time_hist.append(time.time() - t0)
            present = rms > args.threshold
            color = "#d1495b" if present else "#2a9d8f"
            verdict = "사람 있음" if present else "사람 없음"
            print(f"  rms={rms:.3f}  ->  {verdict}")

            ax_wave.clear()
            ax_wave.plot(t, wave, color=color, lw=1.2)
            ax_wave.set_title(f"호흡 대역 위상 파형 ({args.low}~{args.high}Hz, 최근 {span:.0f}초)")
            ax_wave.set_xlabel("시간 (s)")
            ax_wave.grid(alpha=0.25)

            ax_trend.clear()
            ax_trend.plot(list(time_hist), list(rms_hist), "-o", ms=3,
                          color=color, lw=1.5)
            ax_trend.axhline(args.threshold, color="gray", ls="--", lw=1,
                             label=f"임계값 {args.threshold}")
            ax_trend.set_title(f"대역 에너지 추이 — 현재 {rms:.3f}  →  {verdict}")
            ax_trend.set_xlabel("경과 시간 (s)")
            ax_trend.set_ylabel("위상 rms")
            ax_trend.legend(loc="upper right")
            ax_trend.grid(alpha=0.25)

            fig.tight_layout()
            plt.pause(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        subprocess.run(["ssh", "-O", "exit", "-o", f"ControlPath={ctl}",
                        f"{args.user}@{args.host}"],
                       capture_output=True)
        print("\n종료했습니다.")


if __name__ == "__main__":
    main()
