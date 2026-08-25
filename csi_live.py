#!/usr/bin/env python3
"""
CSI 실시간 모니터 — tcpdump 출력을 SSH 파이프로 계속 받아 즉시 그린다.

이전 버전은 5초씩 끊어 캡처하고 파일을 통째로 받아왔다. 캡처가 끝날 때까지
아무것도 안 보이고 SSH 왕복이 매번 붙어 지연이 심했다.
이 버전은 tcpdump `-U -w -` (패킷마다 flush)를 파이프로 받아 스트림 파서로
프레임이 도착하는 즉시 버퍼에 넣는다. 파형은 곧바로 흐르기 시작한다.

다만 대역 에너지(재실 판정)는 여전히 30초 창이 필요하다. 호흡이 0.2Hz라
그보다 짧으면 값이 의미가 없다. 시작 후 30초는 파형만 보이고 판정은 유보된다.

사용법:
    source config.sh && python3 csi_live.py
"""
import argparse
import os
import subprocess
import sys
import threading
from collections import deque

import numpy as np

from csi_pipeline import sanitize_phase, resample_uniform, bandpass_filter
from csi_stream import iter_frames

# 직접 파서 기준 30초 창 실측 (2026-08-26 배치, ping -i 0.05):
#   빈 방   0.519 ~ 0.733
#   사람4명 0.709 ~ 1.215
# 한 창이 겹치므로 그 중간보다 살짝 위로 잡는다.
# ⚠️ 배치나 ping이 바뀌면 빈 방을 다시 찍어 재보정할 것.
DEFAULT_THRESHOLD = 0.75

TCPDUMP = "sudo tcpdump -i wlan0 dst port 5500 -U -w - 2>/dev/null"


class Collector(threading.Thread):
    """SSH 파이프에서 CSI 프레임을 계속 읽어 버퍼에 쌓는 스레드."""

    def __init__(self, host, user, window_s):
        super().__init__(daemon=True)
        self.window_s = window_s
        self.frames = deque()
        self.lock = threading.Lock()
        self.error = None
        self.count = 0
        self.proc = subprocess.Popen(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=5",
             f"{user}@{host}", TCPDUMP],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)

    def run(self):
        try:
            for ts, csi in iter_frames(self.proc.stdout):
                with self.lock:
                    self.frames.append((ts, csi))
                    self.count += 1
                    # 창 길이의 1.5배까지만 보관
                    while self.frames and ts - self.frames[0][0] > self.window_s * 1.5:
                        self.frames.popleft()
        except Exception as e:      # 파이프가 끊기면 여기로
            self.error = e

    def snapshot(self):
        with self.lock:
            if not self.frames:
                return None, None
            t = np.array([f[0] for f in self.frames])
            c = np.stack([f[1] for f in self.frames])
        return t, c

    def stop(self):
        try:
            self.proc.terminate()
        except Exception:
            pass


def analyze(t, csi, low, high, window_s, max_sub=80):
    """(파형 시간축, 파형, 대역 rms, 실측 fs) — 데이터가 모자라면 None."""
    span = t[-1] - t[0]
    if span < 12 or len(t) < 200:
        return None, None, None, None

    phase = sanitize_phase(np.angle(csi))
    # 계산량을 줄이려고 변동 큰 서브캐리어만 쓴다
    if phase.shape[1] > max_sub:
        keep = np.argsort(phase.std(axis=0))[::-1][:max_sub]
        phase = phase[:, np.sort(keep)]

    fs = (len(t) - 1) / span
    _, first = resample_uniform(t, phase[:, 0], fs)
    mat = np.empty((len(first), phase.shape[1]))
    for i in range(phase.shape[1]):
        _, mat[:, i] = resample_uniform(t, phase[:, i], fs)

    filtered = np.apply_along_axis(
        lambda y: bandpass_filter(y, fs, low=low, high=high), 0, mat)
    edge = int(3 * fs)
    if filtered.shape[0] <= 2 * edge:
        return None, None, None, fs
    trimmed = filtered[edge:-edge]

    rms = np.median(trimmed.std(axis=0)) if span >= window_s * 0.8 else None

    top = np.argsort(trimmed.std(axis=0))[::-1][:20]
    seg = trimmed[:, top]
    ref = seg[:, 0]
    signs = np.sign([np.corrcoef(ref, seg[:, i])[0, 1] for i in range(seg.shape[1])])
    signs[signs == 0] = 1
    wave = (seg * signs).mean(axis=1)
    return np.arange(len(wave)) / fs, wave, rms, fs


def main():
    ap = argparse.ArgumentParser(description="CSI 실시간 모니터 (스트리밍)")
    ap.add_argument("--host", default=os.environ.get("PI_HOST", "raspberrypi.local"))
    ap.add_argument("--user", default=os.environ.get("PI_USER", "pi"))
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--window", type=float, default=30, help="분석 창 (초)")
    ap.add_argument("--low", type=float, default=0.15)
    ap.add_argument("--high", type=float, default=0.6)
    ap.add_argument("--fps", type=float, default=2, help="화면 갱신 (초당)")
    ap.add_argument("--history", type=int, default=200)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("MacOSX" if sys.platform == "darwin" else "TkAgg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "AppleGothic"
    plt.rcParams["axes.unicode_minus"] = False

    print(f"{args.user}@{args.host} 스트리밍 시작. 창을 닫으면 종료합니다.")
    col = Collector(args.host, args.user, args.window)
    col.start()

    fig, (ax_wave, ax_trend) = plt.subplots(2, 1, figsize=(11, 7))
    fig.canvas.manager.set_window_title("CSI 실시간 모니터")
    rms_hist, t_hist = deque(maxlen=args.history), deque(maxlen=args.history)
    import time
    t0 = time.time()

    plt.ion()
    plt.show(block=False)
    try:
        while plt.fignum_exists(fig.number):
            if col.error:
                print(f"[오류] 스트림 끊김: {col.error}")
                break
            t, c = col.snapshot()
            if t is None or len(t) < 100:
                plt.pause(1.0 / args.fps)
                continue

            x, wave, rms, fs = analyze(t, c, args.low, args.high, args.window)
            if wave is None:
                span = t[-1] - t[0]
                print(f"\r  버퍼 {span:4.1f}s / {args.window:.0f}s  ({col.count}프레임)",
                      end="", flush=True)
                plt.pause(1.0 / args.fps)
                continue

            if rms is None:
                verdict, color = "판정 대기 (30초 필요)", "#8d99ae"
            else:
                present = rms > args.threshold
                verdict = "사람 있음" if present else "사람 없음"
                color = "#d1495b" if present else "#2a9d8f"
                rms_hist.append(rms)
                t_hist.append(time.time() - t0)

            ax_wave.clear()
            ax_wave.plot(x, wave, color=color, lw=1.2)
            ax_wave.set_title(f"호흡 대역 위상 파형  ({args.low}~{args.high}Hz, "
                              f"{t[-1]-t[0]:.0f}초, {fs:.0f}Hz, {col.count}프레임)")
            ax_wave.set_xlabel("시간 (s)")
            ax_wave.grid(alpha=0.25)

            ax_trend.clear()
            if rms_hist:
                ax_trend.plot(list(t_hist), list(rms_hist), "-", color=color, lw=1.6)
            ax_trend.axhline(args.threshold, color="gray", ls="--", lw=1,
                             label=f"임계값 {args.threshold}")
            now = f"{rms:.3f}" if rms is not None else "—"
            ax_trend.set_title(f"대역 에너지 추이 — 현재 {now}  →  {verdict}")
            ax_trend.set_xlabel("경과 시간 (s)")
            ax_trend.set_ylabel("위상 rms")
            ax_trend.legend(loc="upper right")
            ax_trend.grid(alpha=0.25)

            fig.tight_layout()
            plt.pause(1.0 / args.fps)
    except KeyboardInterrupt:
        pass
    finally:
        col.stop()
        print("\n종료했습니다.")


if __name__ == "__main__":
    main()
