"""faster-whisper large-v3 on the second RTX 4090, Romanian forced.

DLL handling copied from automations/whisper_smoke.py: CTranslate2 needs the
pip-installed NVIDIA cuBLAS/cuDNN bin dirs on the DLL search path on Windows.
Falls back to GPU 0, then CPU int8, and says so in `describe()`.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("jarvis.stt")


def _add_nvidia_dlls() -> int:
    n = 0
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            bin_dir = os.path.join(list(spec.submodule_search_locations)[0], "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
                n += 1
    return n


class Transcriber:
    def __init__(self, cfg: dict[str, Any]):
        _add_nvidia_dlls()
        from faster_whisper import WhisperModel
        self.cfg = cfg
        attempts = [
            (cfg.get("device", "cuda"), int(cfg.get("device_index", 0)), cfg.get("compute_type", "float16")),
            ("cuda", 0, "float16"),
            ("cpu", 0, "int8"),
        ]
        last_err: Exception | None = None
        for device, idx, ctype in attempts:
            try:
                t0 = time.perf_counter()
                self.model = WhisperModel(cfg.get("model", "large-v3"), device=device, device_index=idx, compute_type=ctype)
                self.device = f"{device}:{idx}/{ctype}"
                self.load_s = round(time.perf_counter() - t0, 1)
                return
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning("whisper on %s:%s failed: %s", device, idx, e)
        raise RuntimeError(f"whisper could not load: {last_err}")

    def describe(self) -> dict[str, Any]:
        return {"model": self.cfg.get("model"), "device": self.device, "load_s": self.load_s, "language": self.cfg.get("language")}

    def transcribe_bytes(self, data: bytes, filename: str) -> dict[str, Any]:
        suffix = Path(filename).suffix or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(data)
            path = f.name
        try:
            return self.transcribe_file(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def transcribe_file(self, path: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        segments, info = self.model.transcribe(
            path,
            language=self.cfg.get("language", "ro"),
            beam_size=int(self.cfg.get("beam_size", 5)),
            vad_filter=True,
            initial_prompt=self.cfg.get("initial_prompt"),
        )
        parts = [s.text.strip() for s in segments]
        text = " ".join(p for p in parts if p)
        return {"text": text, "language": info.language, "language_probability": round(info.language_probability, 2),
                "audio_s": round(info.duration, 1), "took_s": round(time.perf_counter() - t0, 2)}
