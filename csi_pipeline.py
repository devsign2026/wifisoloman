#!/usr/bin/env python3
"""
CSI pcap -> 호흡수(BPM) 추정 파이프라인.

pcap 파싱(CSIKit, Nexmon 포맷) -> 진폭 추출 -> 변동 큰 서브캐리어 선택
-> 등간격 재샘플링 -> 밴드패스 필터(0.15~0.6Hz) -> FFT -> 피크 주파수 -> BPM

사용법:
    python3 csi_pipeline.py data/csi_test.pcap
    python3 csi_pipeline.py data/breath_15bpm.pcap --plot out.png
"""
import argparse
import numpy as np
from scipy import signal as sp_signal

from CSIKit.reader import get_reader
from CSIKit.util import csitools


def load_amplitude(pcap_path):
    """
    pcap -> (timestamps[N], amplitude[N, subcarriers])

    tcpdump가 -c 로 끊길 때 캡처 끝에 잘린 레코드가 남는다. 그런 프레임은
    타임스탬프가 0이고 서브캐리어가 전부 non-finite인데, 하나만 섞여도
    "모든 프레임에서 유효한 서브캐리어" 조건이 전멸하므로 여기서 걷어낸다.
    """
    reader = get_reader(pcap_path)
    data = reader.read_file(pcap_path)
    csi_matrix, no_frames, no_subcarriers = csitools.get_CSI(data)
    # CSIKit shape: (frames, subcarriers, rx, tx) -> 안테나 1개 가정
    amplitude = csi_matrix[:, :, 0, 0]
    timestamps = np.array(data.timestamps, dtype=np.float64)

    good = np.isfinite(timestamps) & (timestamps > 0)
    good &= np.isfinite(amplitude).any(axis=1)   # 전부 non-finite인 프레임 제거
    # 타임스탬프는 단조증가여야 한다 (역행하면 그 지점부터 신뢰 불가)
    idx = np.flatnonzero(good)
    if len(idx) == 0:
        raise ValueError(f"{pcap_path}: 유효한 프레임이 없습니다")
    regress = np.flatnonzero(np.diff(timestamps[idx]) < 0)
    if len(regress):
        idx = idx[: regress[0] + 1]

    dropped = len(timestamps) - len(idx)
    if dropped:
        print(f"[정보] 손상 프레임 {dropped}개 제외 ({len(timestamps)} -> {len(idx)})")
    return timestamps[idx], amplitude[idx]


def usable_subcarriers(amplitude, edge_guard=6, max_bad_frac=0.01):
    """
    쓸 수 있는 서브캐리어의 인덱스와, 결측을 메운 진폭 행렬을 반환.

    null/DC 서브캐리어는 진폭 0 -> dB에서 -inf이므로 제외해야 한다.
    단 "모든 프레임에서 유한" 을 요구하면 캡처가 길수록 불리해진다.
    프레임이 많아질수록 어느 서브캐리어든 -inf 를 한 번쯤 만날 확률이 커져,
    100초 캡처에서 유효 서브캐리어가 83/256 까지 떨어지는 현상이 있었다.
    (22초에서는 166개) -> 길이가 다른 캡처끼리 비교가 깨진다.

    그래서 결측 비율이 max_bad_frac 이하인 서브캐리어는 살리고,
    드문 -inf 는 시간축 선형보간으로 메운다.
    """
    n_subcarriers = amplitude.shape[1]
    candidates = np.arange(edge_guard, n_subcarriers - edge_guard)

    finite = np.isfinite(amplitude[:, candidates])
    bad_frac = 1.0 - finite.mean(axis=0)
    usable = candidates[bad_frac <= max_bad_frac]
    if len(usable) == 0:
        raise ValueError("쓸 수 있는 서브캐리어가 없습니다 (null 서브캐리어 확인 필요)")

    cleaned = amplitude[:, usable].astype(np.float64, copy=True)
    for col in range(cleaned.shape[1]):
        bad = ~np.isfinite(cleaned[:, col])
        if bad.any():
            good = np.flatnonzero(~bad)
            cleaned[bad, col] = np.interp(np.flatnonzero(bad), good, cleaned[good, col])
    return usable, cleaned


def select_active_subcarriers(amplitude, n_keep=30, edge_guard=6):
    """분산이 큰 서브캐리어 상위 n_keep개 선택."""
    usable, cleaned = usable_subcarriers(amplitude, edge_guard=edge_guard)
    variance = cleaned.var(axis=0)
    return usable[np.argsort(variance)[::-1][:n_keep]]


def remove_outliers(series, n_std=4):
    """평균에서 n_std * std 벗어난 샘플을 선형보간으로 대체."""
    series = series.copy()
    mean, std = series.mean(), series.std()
    if std == 0:
        return series
    bad = np.abs(series - mean) > n_std * std
    if bad.any():
        good_idx = np.flatnonzero(~bad)
        bad_idx = np.flatnonzero(bad)
        series[bad_idx] = np.interp(bad_idx, good_idx, series[good_idx])
    return series


def resample_uniform(timestamps, series, fs):
    """불균일 샘플링(ping jitter) -> 균일 시간축 선형보간."""
    t0, t1 = timestamps[0], timestamps[-1]
    n_samples = int((t1 - t0) * fs)
    uniform_t = t0 + np.arange(n_samples) / fs
    return uniform_t, np.interp(uniform_t, timestamps, series)


def bandpass_filter(series, fs, low=0.15, high=0.6, order=4):
    """
    0.15~0.6Hz 밴드패스.

    하한이 0.15Hz인 이유: 0.15Hz = 분당 9회. 성인 안정 호흡은 12~20회이므로
    그 아래 대역에는 호흡이 존재할 수 없고 느린 몸 움직임(자세 변화 등)만 들어온다.
    하한을 0.1Hz로 두면 이 드리프트가 대역을 점령해, 90초 캡처에서 서브캐리어
    226/243이 밴드 최하단에 몰리는 현상이 생겼다. 0.15로 올리자 같은 캡처가
    0.20Hz / 0.30Hz 로 갈렸고, 빈 방 대조군은 여전히 최하단에 남았다.

    ⚠️ 반드시 SOS(2차 구간) 형태를 쓸 것. 전달함수 계수(b, a) 형태는
    이 대역에서 수치적으로 붕괴한다. fs=78Hz만 돼도 정규화 하한이
    0.1/39 = 0.00256이라 극점 반경이 1.0039 > 1이 되어 필터가 불안정해진다.
    fs=126Hz에서는 filtfilt 출력이 1e8까지 발산했고, 0.25Hz 사인파를
    넣으면 0.133Hz라고 답했다. SOS는 같은 조건에서 0.256Hz로 복원한다.
    """
    nyquist = fs / 2
    sos = sp_signal.butter(order, [low / nyquist, high / nyquist],
                           btype="band", output="sos")
    return sp_signal.sosfiltfilt(sos, series)


def fft_peak_freq(series, fs, low=0.15, high=0.6):
    n = len(series)
    windowed = series * np.hanning(n)
    freqs = np.fft.rfftfreq(n, d=1 / fs)
    spectrum = np.abs(np.fft.rfft(windowed))

    band_mask = (freqs >= low) & (freqs <= high)
    if not band_mask.any():
        raise ValueError("밴드 내 주파수 성분이 없습니다 (fs/윈도 길이 확인 필요)")

    band_freqs = freqs[band_mask]
    band_spectrum = spectrum[band_mask]
    peak_freq = band_freqs[np.argmax(band_spectrum)]
    return peak_freq, freqs, spectrum


def analyze(pcap_path, low=0.15, high=0.6, n_keep=30, plot_path=None):
    timestamps, amplitude = load_amplitude(pcap_path)
    n_frames, n_subcarriers = amplitude.shape

    duration = timestamps[-1] - timestamps[0]
    fs_nominal = (n_frames - 1) / duration
    print(f"[정보] 프레임 수: {n_frames}, 서브캐리어 수: {n_subcarriers}")
    print(f"[정보] 캡처 길이: {duration:.1f}s, 평균 샘플링레이트: {fs_nominal:.1f}Hz")

    if duration < 1 / low:
        print(f"[경고] 캡처 길이가 {1/low:.0f}s보다 짧아 {low}Hz 이하 성분을 신뢰할 수 없습니다.")

    active = select_active_subcarriers(amplitude, n_keep=n_keep)
    combined = amplitude[:, active].mean(axis=1)
    combined = remove_outliers(combined)

    fs = fs_nominal  # 재샘플링 목표 레이트
    uniform_t, uniform_series = resample_uniform(timestamps, combined, fs)
    filtered = bandpass_filter(uniform_series, fs, low=low, high=high)

    peak_freq, freqs, spectrum = fft_peak_freq(filtered, fs, low=low, high=high)
    bpm = peak_freq * 60
    print(f"[결과] 피크 주파수: {peak_freq:.3f}Hz -> 추정 호흡수: {bpm:.1f} BPM")

    if plot_path:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.rcParams["font.family"] = "AppleGothic"
        plt.rcParams["axes.unicode_minus"] = False

        fig, axes = plt.subplots(3, 1, figsize=(10, 8))
        axes[0].plot(uniform_t - uniform_t[0], uniform_series)
        axes[0].set_title("선택된 서브캐리어 평균 진폭 (재샘플링 후)")
        axes[0].set_xlabel("시간 (s)")

        axes[1].plot(uniform_t - uniform_t[0], filtered)
        axes[1].set_title(f"밴드패스 필터 결과 ({low}~{high}Hz)")
        axes[1].set_xlabel("시간 (s)")

        band_mask = (freqs >= 0) & (freqs <= 1.0)
        axes[2].plot(freqs[band_mask], spectrum[band_mask])
        axes[2].axvline(peak_freq, color="r", linestyle="--", label=f"peak={peak_freq:.3f}Hz")
        axes[2].axvspan(low, high, color="g", alpha=0.1, label="관심 대역")
        axes[2].set_title("FFT 스펙트럼")
        axes[2].set_xlabel("주파수 (Hz)")
        axes[2].legend()

        fig.tight_layout()
        fig.savefig(plot_path, dpi=120)
        print(f"[정보] 그래프 저장: {plot_path}")

    return peak_freq, bpm


def main():
    parser = argparse.ArgumentParser(description="CSI pcap -> 호흡수 추정")
    parser.add_argument("pcap", help="입력 pcap 파일 경로")
    parser.add_argument("--low", type=float, default=0.15, help="밴드패스 하한 (Hz). 0.15=9회/분 — 그 아래는 호흡이 아니라 몸 움직임")
    parser.add_argument("--high", type=float, default=0.6, help="밴드패스 상한 (Hz)")
    parser.add_argument("--n-keep", type=int, default=30, help="사용할 서브캐리어 개수")
    parser.add_argument("--plot", default=None, help="그래프 저장 경로 (예: out.png)")
    args = parser.parse_args()

    analyze(args.pcap, low=args.low, high=args.high, n_keep=args.n_keep, plot_path=args.plot)


if __name__ == "__main__":
    main()
