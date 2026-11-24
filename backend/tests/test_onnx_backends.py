"""Exercise the ONNX embedder and reranker code paths with tiny generated models.

No downloads: a fake Hugging Face snapshot (tokenizer.json + model) is built in tmp_path.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import numpy as np
import pytest

onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper  # noqa: E402
from tokenizers import Tokenizer, models, pre_tokenizers, processors  # noqa: E402

VOCAB = {"<s>": 0, "<pad>": 1, "</s>": 2, "<unk>": 3, "한글": 4, "세종": 5, "김치": 6, "창제": 7}


def _tokenizer(path: Path) -> None:
    tok = Tokenizer(models.WordLevel(VOCAB, unk_token="<unk>"))
    tok.pre_tokenizer = pre_tokenizers.Whitespace()
    tok.post_processor = processors.TemplateProcessing(
        single="<s> $A </s>", pair="<s> $A </s> </s> $B </s>",
        special_tokens=[("<s>", 0), ("</s>", 2)])
    tok.save(str(path / "tokenizer.json"))


def _model(path: Path, output: str, dim: int) -> None:
    """output = masked sum of token embeddings -> [batch, dim]."""
    emb = np.random.RandomState(0).rand(len(VOCAB), dim).astype(np.float32)
    nodes = [
        helper.make_node("Gather", ["E", "input_ids"], ["g"]),
        helper.make_node("Cast", ["attention_mask"], ["m"], to=TensorProto.FLOAT),
        helper.make_node("Unsqueeze", ["m", "ax"], ["m3"]),
        helper.make_node("Mul", ["g", "m3"], ["gm"]),
        helper.make_node("ReduceSum", ["gm", "ax1"], [output], keepdims=0),
    ]
    graph = helper.make_graph(
        nodes, "fake",
        [helper.make_tensor_value_info("input_ids", TensorProto.INT64, ["b", "t"]),
         helper.make_tensor_value_info("attention_mask", TensorProto.INT64, ["b", "t"])],
        [helper.make_tensor_value_info(output, TensorProto.FLOAT, ["b", dim])],
        [helper.make_tensor("E", TensorProto.FLOAT, emb.shape, emb.flatten()),
         helper.make_tensor("ax", TensorProto.INT64, [1], [2]),
         helper.make_tensor("ax1", TensorProto.INT64, [1], [1])])
    m = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    m.ir_version = 8
    path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(m, str(path))


def test_onnx_embedder_backend(tmp_path: Path):
    from app.retrieval.embedder import OnnxInt8Backend

    _tokenizer(tmp_path)
    _model(tmp_path / "model_quantized.onnx", "dense_vecs", 4)
    with mock.patch("huggingface_hub.snapshot_download", return_value=str(tmp_path)):
        backend = OnnxInt8Backend("x", str(tmp_path), 1, 32)
        vecs = backend.embed(["한글 세종", "김치", "한글 김치 세종 모르는단어"], batch_size=2)
    assert vecs.shape == (3, 4) and backend.output == "dense_vecs"
    # second load uses the saved optimized graph
    assert (tmp_path / "model_quantized.opt.onnx").exists()
    with mock.patch("huggingface_hub.snapshot_download", return_value=str(tmp_path)):
        again = OnnxInt8Backend("x", str(tmp_path), 1, 32).embed(["김치"], batch_size=1)
    assert np.allclose(again[0], vecs[1], atol=1e-5)


def test_onnx_reranker(tmp_path: Path, monkeypatch):
    from app.config import get_settings
    from app.retrieval import reranker as rr
    from app.retrieval.types import RetrievedChunk

    _tokenizer(tmp_path)
    _model(tmp_path / "onnx" / "model_int8.onnx", "logits", 1)
    monkeypatch.setenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3-int8")
    get_settings.cache_clear()
    monkeypatch.setattr(rr, "_instance", None)
    with mock.patch("huggingface_hub.snapshot_download", return_value=str(tmp_path)):
        r = rr.get_reranker()
        assert rr.get_reranker() is r  # loaded once
    chunks = [RetrievedChunk(str(i), "d", "t", "f", 1, "", txt, 0, 1, "ko", True, 0.0, rank=i + 1)
              for i, txt in enumerate(["김치", "한글 세종 창제", "모르는단어"])]
    out = r.rerank("한글", chunks, 3)
    assert len(out) == 3 and all(0.0 <= c.score <= 1.0 for c in out)
    assert [c.rank for c in out] == [1, 2, 3]
    assert out[0].scores["fused_rank"] in (1, 2, 3)
    get_settings.cache_clear()
