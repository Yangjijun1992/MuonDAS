# Main-Pulse Peak-Finding Code (pmt_analysis · After-Pulse Analysis)

This document lists the **main-pulse (寻峰) peak-finding related code** from the
`pmt_analysis` repo, for other repos (e.g. MuonDAS) to read and reuse.

Source repo: `https://github.com/Yangjijun1992/pmt_analysis`
Analysis entry: after-pulse analysis (`analyze_app`) in
`src/pmt_analysis/analysis/app.py`.

---

## 1. Core main-pulse peak finding (`src/pmt_analysis/analysis/app.py`)

| Function | Line | Purpose |
|----------|------|---------|
| `preprocess_waveform(waveform)` | 168 | Baseline subtraction: `waveform - mean(first 30 samples)`; returns `(processed, baseline)`. |
| `cal_area(waveform, st, ed, baseline)` | 111 | Pulse charge/area: `baseline*(ed-st) - sum(waveform[st:ed])`, scaled by `PE_FACT` (ADC → PE). |
| `findpulse_st_ed(waveform, baseline, reference_point, search_range=5)` | 119 | Finds a single pulse's `(start, min_index, end)` around a reference point: local minimum within ±5 samples, then walk left/right to pulse boundaries. |
| **`find_main_pulses_per_channel(bundle, height_threshold=1000)`** | 174 | **Main algorithm.** For each waveform: preprocess → `argmin` → height check (`abs(min) >= 1000 ADC`) → walk left to start → walk right to end (3 consecutive samples within 50 ADC of baseline) → `cal_area` → `MainPulseRecord`. Groups by `(board, channel)`. |
| `find_afterpulse_candidates_per_channel(...)` | 238 | After main pulse end + 35 samples, threshold crossing at `<-20 ADC`, dedup 2 samples apart, then `findpulse_st_ed` per candidate. (Secondary peak finding.) |
| `MainPulseRecord` (dataclass) | 43 | Output record: `event_index, channel_index, sample_index, height, charge, charge_pe, start, end, baseline, metadata`. |
| `analyze_app(...)` | 1083 | Full APP pipeline orchestrator (Step 1 = main pulse detection). |

**Key thresholds (defaults, top of `app.py`):**
- `DEFAULT_MAIN_PULSE_HEIGHT_THRESHOLD = 1000` ADC — main pulse height cut
- `DEFAULT_AMPLITUDE_THRESHOLD = 20` ADC — afterpulse threshold
- `DEFAULT_AFTERPULSE_MIN_INTERVAL = 35` samples — search gap after main pulse
- `DEFAULT_MIN_INTERVAL_BETWEEN_PULSES = 10` samples — afterpulse de-dup interval

---

## 2. Noise-suppressed variant (`src/pmt_analysis/analysis/app_noise_suppress.py`)

Used for channels with baseline RMS ≥ 5 ADC (big-wave noise). Re-detects
afterpulses on a dynamic-baseline-corrected waveform; still takes the main
pulse `start/end` from `find_main_pulses_per_channel` as input.

| Function | Line | Purpose |
|----------|------|---------|
| `compute_channel_baseline_stats(waveforms_by_ch)` | 83 | Baseline RMS per channel (std of first 30 samples) — noise channel flagging. |
| `detect_noisy_channels(waveforms_by_ch, rms_threshold=5.0)` | 111 | Returns set of channels with baseline RMS ≥ threshold. |
| `_generate_main_pulse_mask(length, main_pulse_start, main_pulse_end)` | 171 | Boolean mask that blanks the main-pulse region for baseline fitting. |
| `_extract_baseline_median(waveform, mask, window_size=51)` | 199 | Sliding-median dynamic baseline (NaN gaps interpolated). |
| `_check_event_quality(waveform, main_pulse_end, quality_rms_threshold)` | 141 | Rejects events with peak-to-peak > threshold in afterglow window. |
| `_find_afterpulses_with_suppression(...)` | 257 | Dynamic-threshold (`-N·RMS`) + slope-check afterpulse search. |
| `_process_event_with_noise_suppression(...)` | 400 | Full per-event pipeline: quality → mask → baseline → search. |
| `find_afterpulses_with_noise_suppression(...)` | 508 | Top-level for noisy channels. |

---

## 3. Parallel (multi-process) variant (`src/pmt_analysis/analysis/app_parallel.py`)

Event-block parallel APP (same main-pulse algorithm, split over processes).

| Function | Line | Purpose |
|----------|------|---------|
| `_find_main_pulses_in_block(waveforms, records, indices, height_threshold)` | 113 | Identical main-pulse logic to `find_main_pulses_per_channel`, but on a pre-loaded waveform block. |
| `_find_afterpulse_candidates_in_block(...)` | 176 | Afterpulse candidate search per block. |
| `_findpulse_st_ed(waveform, reference_point, search_range=5)` | 269 | Local copy of the pulse-boundary finder for worker processes. |
| `bulk_load_waveforms(bundle)` | 73 | Loads all waveforms once (`rv.signals(all_ids)`) into a contiguous array. |
| `analyze_app_parallel(bundle, n_workers, ...)` | 375 | Orchestrator: block partition → Pool.map → merge → reuse serial post-processing. |

---

## 4. Summary: main-pulse algorithm flow

```
waveform (raw)
  → preprocess_waveform()          # - mean(first 30 samples)
  → argmin(processed)              # pulse minimum position
  → height check >= 1000 ADC       # DEFAULT_MAIN_PULSE_HEIGHT_THRESHOLD
  → walk LEFT to pulse start       # while processed[start] <= processed[start-1]
  → walk RIGHT to pulse end        # 3 consecutive |processed| < 50 ADC
  → cal_area()                     # baseline*(ed-st) - sum, * PE_FACT
  → MainPulseRecord(sample_index, height, charge, start, end, baseline)
```

Afterpulse search then scans `[main_pulse.end + 35, end)` for threshold
crossings below `-20 ADC`, fits each via `findpulse_st_ed`, applies a 10-sample
minimum interval, and (for noisy channels) replaces results with the
noise-suppressed search from `app_noise_suppress.py`.

---

## 5. Reuse notes for other repos

- Pure numpy, no DAQ-specific dependency inside the core functions —
  `findpulse_st_ed`, `cal_area`, `preprocess_waveform`, and the
  `find_main_pulses_*` logic can be copied directly given a 1-D waveform array.
- `PE_FACT` (ADC→PE) is PMT-ADC-specific:
  `PE_FACT = (2/16384) * 4e-9 / (50 * 1.6e-19) / 1e6`.
- The parallel variant requires Linux `fork` for shared-memory waveform access.
- Default thresholds are tunable keyword arguments on every entry point.
