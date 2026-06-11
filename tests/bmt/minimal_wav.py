"""Valid minimal PCM WAV fixtures (stdlib ``wave``) for unit tests."""

from __future__ import annotations

import wave
from pathlib import Path


def write_minimal_pcm_wav(
    path: Path,
    *,
    channels: int = 1,
    frames: int = 8,
    sample_rate: int = 16_000,
    sampwidth: int = 2,
) -> None:
    """Write a tiny silent PCM16 WAV that passes RIFF probe and ``wave.open`` reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    silence = b"\x00" * (frames * channels * sampwidth)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(silence)
