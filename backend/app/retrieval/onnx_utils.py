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
        except Exception:  # corrupted/partial file: rebuild it below
            log.warning("Optimized model %s unreadable, rebuilding", optimized.name)
            optimized.unlink(missing_ok=True)

    # First run: optimize once and save. Fall back to basic optimization if memory is tight.
    for level in (ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
                  ort.GraphOptimizationLevel.ORT_ENABLE_BASIC):
        opts.graph_optimization_level = level
        opts.optimized_model_filepath = str(optimized)
        try:
            session = ort.InferenceSession(str(model_path), opts, providers=providers)
            log.info("Saved optimized model to %s", optimized)
            return session
        except Exception as e:  # noqa: BLE001
            log.warning("Loading %s with %s failed (%s); retrying lighter", model_path.name,
                        level, e)
            optimized.unlink(missing_ok=True)
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
    opts.optimized_model_filepath = ""
    return ort.InferenceSession(str(model_path), opts, providers=providers)
