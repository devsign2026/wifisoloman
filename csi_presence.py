#!/usr/bin/env python3
"""
CSI 위상 기반 재실 감지.

호흡 대역(0.15~0.6Hz) 위상 변동의 크기로 사람이 있는지 판정한다.
'호흡수'가 아니라 '사람이 있느냐'를 본다 — 이 대역에는 호흡뿐 아니라
미세한 몸 움직임도 들어오므로, 검출되는 것은 재실이지 호흡 그 자체가 아니다.

왜 위상인가: 같은 A/B 캡처(빈 방 7분 vs 사람 4명 7분, 동일 조건)에서
  진폭 기반 -> 빈 방 1.954 / 사람 1.829, p=0.900 (구분 실패, 방향도 반대)
  위상 기반 -> 빈 방 0.57  / 사람 0.99,  p<0.001, 겹침 0/13, Cohen d=3.19

사용법:
    python3 csi_presence.py data/occupied4_20260826.pcap
    python3 csi_presence.py A.pcap --compare B.pcap    # 두 캡처 통계 비교
"""
import argparse
import numpy as np

from csi_pipeline import (load_phase, sanitize_phase, resample_uniform,
                          bandpass_filter)

# 빈 방 7분(2026-08-26, 창 13개)의 관측 범위 0.47~0.76,
# 사람 4명의 관측 범위 0.80~1.27 사이 중간값.
# ⚠️ 배치가 바뀌면 기준선을 다시 찍고 이 값을 갱신할 것.
DEFAULT_THRESHOLD = 0.78


def band_rms_windows(pcap_path, window_s=30, low=0.15, high=0.6, edge_s=3):
    """30초 창마다 호흡 대역 위상 변동의 rms(서브캐리어 중앙값)를 반환."""
    timestamps, phase = load_phase(pcap_path)
    clean = sanitize_phase(phase)

    fs = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
    _, first = resample_uniform(timestamps, clean[:, 0], fs)
    resampled = np.empty((len(first), clean.shape[1]))
    for i in range(clean.shape[1]):
        _, resampled[:, i] = resample_uniform(timestamps, clean[:, i], fs)

    width = int(window_s * fs)
    edge = int(edge_s * fs)
    if width - 2 * edge < 2:
        raise ValueError("창이 너무 짧습니다")

    values = []
    for start in range(0, len(resampled) - width + 1, width):
        seg = resampled[start:start + width]
        filtered = np.apply_along_axis(
            lambda y: bandpass_filter(y, fs, low=low, high=high), 0, seg)
        # filtfilt 가장자리 과도응답 구간은 버린다
        values.append(np.median(filtered[edge:-edge].std(axis=0)))
    return np.array(values), fs


def report(pcap_path, threshold, window_s):
    values, fs = band_rms_windows(pcap_path, window_s=window_s)
    median = np.median(values)
    print(f"[정보] {pcap_path}")
    print(f"[정보] {fs:.0f}Hz, {window_s:.0f}초 창 {len(values)}개")
    print(f"[정보] 창별 rms: {' '.join(f'{v:.2f}' for v in values)}")
    print(f"[결과] 중앙값 {median:.3f}  (임계값 {threshold})")
    above = (values > threshold).sum()
    if median > threshold:
        print(f"[판정] 사람 있음 — 창 {above}/{len(values)}개가 임계값 초과")
    else:
        print(f"[판정] 사람 없음 — 창 {above}/{len(values)}개만 임계값 초과")
    return values


def compare(path_a, path_b, window_s):
    from scipy import stats
    a, _ = band_rms_windows(path_a, window_s=window_s)
    b, _ = band_rms_windows(path_b, window_s=window_s)
    print(f"\n{'':14s}{'중앙값':>10s}{'최소':>8s}{'최대':>8s}{'창':>5s}")
    print("-" * 46)
    for name, x in ((path_a, a), (path_b, b)):
        label = name.split("/")[-1][:13]
        print(f"{label:14s}{np.median(x):>10.3f}{x.min():>8.2f}{x.max():>8.2f}{len(x):>5d}")

    hi, lo = (a, b) if np.median(a) > np.median(b) else (b, a)
    overlap = (hi <= lo.max()).sum()
    pooled = np.sqrt((a.var() + b.var()) / 2)
    d = abs(np.median(a) - np.median(b)) / pooled if pooled else float("inf")
    p = stats.mannwhitneyu(hi, lo, alternative="greater").pvalue
    print(f"\n  겹침 {overlap}/{len(hi)}개   Cohen d={d:.2f}   Mann-Whitney p={p:.4f}")
    if overlap == 0 and p < 0.05:
        print("  → 두 캡처는 완전히 분리됨")
    elif p < 0.05:
        print("  → 유의하게 다르나 일부 겹침")
    else:
        print("  → 구분되지 않음")


def main():
    parser = argparse.ArgumentParser(description="CSI 위상 기반 재실 감지")
    parser.add_argument("pcap", help="입력 pcap")
    parser.add_argument("--compare", default=None, help="비교할 다른 pcap")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"재실 판정 임계값 (기본 {DEFAULT_THRESHOLD})")
    parser.add_argument("--window", type=float, default=30, help="창 길이 (초)")
    args = parser.parse_args()

    report(args.pcap, args.threshold, args.window)
    if args.compare:
        compare(args.pcap, args.compare, args.window)


if __name__ == "__main__":
    main()
