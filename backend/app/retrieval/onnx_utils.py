"""Memory-conscious ONNX Runtime sessions for small machines.

Loading a transformer with full graph optimization can briefly need 2 to 3 times the
model's size in RAM (the optimizer rewrites the graph in memory). On an 8 GB laptop that
spike is what failed with "bad allocation". So we:
  1. optimize once with ORT_ENABLE_ALL and save the optimized graph next to the model,
  2. on later starts, load the saved graph with optimizations disabled (no spike),
  3. turn off the CPU memory arena, which otherwise keeps peak allocations forever.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def make_session(model_path: Path, threads: int):  # type: ignore[no-untyped-def]
    import onnxruntime as ort

    optimized = model_path.with_name(model_path.stem + ".opt.onnx")
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.enable_cpu_mem_arena = False
    opts.enable_mem_pattern = False
    providers = ["CPUExecutionProvider"]

    if optimized.exists():
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        try:
            return ort.InferenceSession(str(optimized), opts, providers=providers)
        except Exception as e:
            # Usually "bad allocation" (not enough free RAM), which says nothing about the
            # file. Never delete it here; report the real cause instead of retrying heavier.
            if _is_memory_error(e):
                raise MemoryError(
                    f"Not enough free memory to load {model_path.name}. Close other apps "
                    "(browsers use the most) or enlarge the Windows paging file.") from e
            log.warning("Optimized model %s failed to load (%s); using the original",
                        optimized.name, e)
            return _load_plain(model_path, opts, providers)

    # First run: optimize once and save. Fall back to basic optimization if memory is tight.
    last: Exception | None = None
    for level in (ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
                  ort.GraphOptimizationLevel.ORT_ENABLE_BASIC):
        opts.graph_optimization_level = level
        opts.optimized_model_filepath = str(optimized)
        try:
            session = ort.InferenceSession(str(model_path), opts, providers=providers)
            log.info("Saved optimized model to %s", optimized)
            return session
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("Loading %s with %s failed (%s); retrying lighter", model_path.name,
                        level, e)
            optimized.unlink(missing_ok=True)  # a half-written file from this attempt
    if last is not None and _is_memory_error(last):
        raise MemoryError(
            f"Not enough free memory to load {model_path.name}. Close other apps "
            "(browsers use the most) or enlarge the Windows paging file.") from last
    opts.optimized_model_filepath = ""
    return _load_plain(model_path, opts, providers)


def _load_plain(model_path: Path, opts, providers):  # type: ignore[no-untyped-def]
    import onnxruntime as ort

    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    opts.optimized_model_filepath = ""
    return ort.InferenceSession(str(model_path), opts, providers=providers)


def _is_memory_error(e: Exception) -> bool:
    msg = str(e).lower()
    return isinstance(e, MemoryError) or "bad allocation" in msg or "bad_alloc" in msg
