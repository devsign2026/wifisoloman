#!/usr/bin/env python3
"""
CSI pcap 진단 — "호흡 신호가 데이터에 있기는 한가?"를 먼저 판정.

csi_pipeline.py는 서브캐리어를 결합해 BPM 하나를 뱉는다. 신호가 없어도
숫자는 나오므로, 그 숫자만 보면 잡음을 호흡으로 오독하게 된다.
이 스크립트는 결합 전에 서브캐리어를 개별로 훑어 피크 주파수 분포를 보여준다.

판정 기준:
  - 밴드 0.1~0.6Hz에서 ±0.02Hz 구간이 우연히 맞을 확률 ≈ 8%
  - 히트율이 8%를 유의미하게 넘어야 신호가 있는 것
  - 피크가 밴드 최하단(0.10Hz)에 몰리면 호흡이 아니라 느린 드리프트

사용법:
    python3 csi_diagnose.py data/breath_15bpm.pcap --expect 15
    python3 csi_diagnose.py data/baseline_empty.pcap
"""
import argparse
import numpy as np

from csi_pipeline import load_amplitude, resample_uniform, bandpass_filter

CHANCE_RATE = 0.08  # 밴드 0.1~0.6Hz에서 ±0.02Hz가 우연히 맞을 확률


def subcarrier_peaks(pcap_path, low=0.1, high=0.6, edge_guard=6, seconds=None):
    """서브캐리어별로 밴드패스 + FFT -> (피크주파수[], 선명도[], fs, 길이)"""
    timestamps, amplitude = load_amplitude(pcap_path)

    # 길이가 다른 캡처끼리 비교하려면 같은 초로 잘라야 한다.
    # 짧은 캡처는 밴드 하한 근처에서 필터 과도응답이 지배해 분포가 왜곡되므로,
    # 길이를 안 맞추고 비교하면 환경 차이가 아니라 길이 차이를 보게 된다.
    if seconds is not None:
        keep = timestamps <= timestamps[0] + seconds
        if keep.sum() < 2:
            raise ValueError(f"--seconds {seconds}가 캡처보다 깁니다")
        timestamps, amplitude = timestamps[keep], amplitude[keep]

    usable = np.isfinite(amplitude).all(axis=0)
    usable[:edge_guard] = False
    usable[-edge_guard:] = False
    valid = amplitude[:, usable]
    if valid.shape[1] == 0:
        raise ValueError("유효한 서브캐리어가 없습니다")

    fs = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])

    uniform_t, first = resample_uniform(timestamps, valid[:, 0], fs)
    filtered = np.empty((len(first), valid.shape[1]))
    for i in range(valid.shape[1]):
        _, series = resample_uniform(timestamps, valid[:, i], fs)
        filtered[:, i] = bandpass_filter(series, fs, low=low, high=high)

    window = np.hanning(filtered.shape[0])[:, None]
    spectrum = np.abs(np.fft.rfft(filtered * window, axis=0))
    freqs = np.fft.rfftfreq(filtered.shape[0], d=1 / fs)

    band = (freqs >= low) & (freqs <= high)
    band_freqs, band_spec = freqs[band], spectrum[band]

    peaks = band_freqs[np.argmax(band_spec, axis=0)]
    # 선명도: 피크 / 밴드 중앙값. 호흡이면 뾰족하고, 잡음이면 1에 가깝다.
    sharpness = band_spec.max(axis=0) / np.median(band_spec, axis=0)
    return peaks, sharpness, fs, filtered.shape[0] / fs


def diagnose(pcap_path, expect_bpm=None, low=0.1, high=0.6, tol=0.02, seconds=None):
    peaks, sharpness, fs, duration = subcarrier_peaks(
        pcap_path, low=low, high=high, seconds=seconds)

    print(f"[정보] {pcap_path}")
    print(f"[정보] 서브캐리어 {len(peaks)}개, {fs:.0f}Hz, {duration:.0f}s")
    cycles = duration * low
    if cycles < 5:
        print(f"[경고] {low}Hz 성분이 {cycles:.1f}주기밖에 안 들어감 "
              f"-> 밴드 하한 쏠림은 필터 과도응답일 수 있음. 최소 {5/low:.0f}s 권장")

    edges = np.arange(low, high + 0.05, 0.05)
    hist, _ = np.histogram(peaks, bins=edges)
    print("[분포] 피크 주파수별 서브캐리어 수")
    for i, count in enumerate(hist):
        if count:
            bar = "#" * int(40 * count / hist.max())
            print(f"       {edges[i]:.2f}Hz {count:4d}  {bar}")

    bottom = (peaks <= low + 0.005).sum()
    if bottom > len(peaks) * 0.5:
        print(f"[경고] {bottom}/{len(peaks)}개가 밴드 최하단({low}Hz)에 몰림")
        print(f"       -> 호흡이 아니라 느린 드리프트가 지배. 캡처 중 자세 변화/환경 변동 의심")

    print(f"[정보] 피크 선명도 중앙값 {np.median(sharpness):.2f}")

    if expect_bpm is None:
        print("[판정] --expect 미지정 (기준선 캡처면 정상). 위 분포를 호흡 캡처와 비교할 것")
        return None

    target = expect_bpm / 60
    hits = (np.abs(peaks - target) < tol).sum()
    rate = hits / len(peaks)
    print(f"[결과] 정답 {target:.3f}Hz(±{tol}) 히트: {hits}/{len(peaks)} ({rate*100:.0f}%)")
    print(f"       우연 수준 ≈ {CHANCE_RATE*100:.0f}%")

    if rate < CHANCE_RATE:
        print("[판정] ❌ 우연보다 낮음 — 호흡 신호 없음. 알고리즘 손대지 말고 재캡처할 것")
    elif rate < CHANCE_RATE * 2:
        print("[판정] ⚠️  우연과 구별 안 됨 — 신호 있다고 말할 수 없음")
    else:
        print("[판정] ✅ 우연을 유의미하게 넘음 — 호흡 신호 있음. 결합 방식 개선이 의미 있는 단계")
    return rate


def main():
    parser = argparse.ArgumentParser(description="CSI pcap에 호흡 신호가 있는지 진단")
    parser.add_argument("pcap", help="입력 pcap 경로")
    parser.add_argument("--expect", type=float, default=None,
                        help="정답 호흡수 (BPM). 생략하면 분포만 출력")
    parser.add_argument("--low", type=float, default=0.1, help="밴드패스 하한 (Hz)")
    parser.add_argument("--high", type=float, default=0.6, help="밴드패스 상한 (Hz)")
    parser.add_argument("--seconds", type=float, default=None,
                        help="앞에서부터 N초만 사용 (길이 다른 캡처끼리 비교할 때)")
    args = parser.parse_args()

    diagnose(args.pcap, expect_bpm=args.expect, low=args.low,
             high=args.high, seconds=args.seconds)


if __name__ == "__main__":
    main()
