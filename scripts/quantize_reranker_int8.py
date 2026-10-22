#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
==============================================================================
  DỰ ÁN: IN-COURSE AGENTIC RAG COPILOT
  SCRIPT: LƯỢNG TỬ HÓA ONNX PTQ INT8 CHO CROSS-ENCODER RE-RANKER (M-05c)
  Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT
==============================================================================
Mục đích:
- Chuyển đổi mô hình Cross-Encoder jina-reranker-v2-base-multilingual từ FP32 (1.11 GB)
  sang INT8 (~280 MB) bằng ONNX Runtime Post-Training Dynamic Quantization (PTQ).
- Lưu trữ mô hình vào data/models/jina-reranker-v2-int8/ để phục vụ suy luận siêu tốc (< 150ms)
  với tập lệnh Intel/AMD AVX2 / AVX-512 VNNI trên CPU.
- Sau khi lượng tử hóa thành công, người dùng có thể xóa an toàn thư mục FP32 tạm thời.
"""

import sys
import shutil
import time
from pathlib import Path

# Đảm bảo UTF-8 cho Windows Terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import onnxruntime as ort
from onnxruntime.quantization import quantize_dynamic, QuantType
from fastembed.common.utils import define_cache_dir


def find_source_fp32_model() -> tuple[Path, Path]:
    """
    Định vị thư mục snapshot chứa mô hình gốc model.onnx trong cache của fastembed.
    """
    cache_root = define_cache_dir()
    jina_cache_dir = cache_root / "models--jinaai--jina-reranker-v2-base-multilingual"
    snapshots_dir = jina_cache_dir / "snapshots"

    if not snapshots_dir.exists():
        raise FileNotFoundError(
            f"[LỖI] Không tìm thấy thư mục snapshot của Jina Re-ranker tại:\n{snapshots_dir}\n"
            f"Hãy đảm bảo bạn đã chạy server hoặc benchmark ít nhất 1 lần để fastembed tải mô hình."
        )

    # Lấy snapshot hash đầu tiên
    snapshot_folders = [p for p in snapshots_dir.iterdir() if p.is_dir()]
    if not snapshot_folders:
        raise FileNotFoundError(f"[LỖI] Không có snapshot hash nào trong {snapshots_dir}")

    snapshot_path = snapshot_folders[0]
    model_onnx_path = snapshot_path / "onnx" / "model.onnx"

    if not model_onnx_path.exists():
        raise FileNotFoundError(f"[LỖI] Không tìm thấy file model.onnx tại:\n{model_onnx_path}")

    return snapshot_path, model_onnx_path


def quantize_reranker_to_int8():
    print("=" * 78)
    print("  TIẾN TRÌNH LƯỢNG TỬ HÓA ONNX PTQ INT8 - JINA RERANKER V2 (M-05c)")
    print("  Tác giả: Trần Thành Nghĩa (MSSV: 23DH112252) - HUFLIT")
    print("=" * 78)

    snapshot_dir, source_onnx_path = find_source_fp32_model()
    source_size_mb = source_onnx_path.stat().st_size / (1024 * 1024)
    print(f"\n[1/4] Đã tìm thấy mô hình gốc FP32:")
    print(f"      Đường dẫn: {source_onnx_path}")
    print(f"      Kích thước ban đầu: {source_size_mb:.2f} MB (~{source_size_mb/1024:.2f} GB)")

    target_dir = REPO_ROOT / "data" / "models" / "jina-reranker-v2-int8"
    target_onnx_dir = target_dir / "onnx"
    target_onnx_dir.mkdir(parents=True, exist_ok=True)
    target_onnx_path = target_onnx_dir / "model.onnx"

    # Sao chép các tệp cấu hình tokenizer cần thiết
    print(f"\n[2/4] Sao chép tệp cấu hình Tokenizer sang {target_dir}...")
    for config_file in ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]:
        src_file = snapshot_dir / config_file
        if src_file.exists():
            shutil.copy2(src_file, target_dir / config_file)
            print(f"      - Đã sao chép: {config_file}")

    # Thực hiện lượng tử hóa động INT8
    print(f"\n[3/4] Đang thực hiện lượng tử hóa Dynamic Quantization sang INT8 (AVX-512/VNNI)...")
    print(f"      (Quá trình này có thể mất từ 1 - 2 phút tùy CPU)...")
    start_time = time.time()

    quantize_dynamic(
        model_input=str(source_onnx_path),
        model_output=str(target_onnx_path),
        weight_type=QuantType.QInt8,
        per_channel=True,
        reduce_range=True,
    )
    elapsed = time.time() - start_time
    target_size_mb = target_onnx_path.stat().st_size / (1024 * 1024)
    compression_ratio = (1.0 - (target_size_mb / source_size_mb)) * 100

    print(f"      [OK] Lượng tử hóa hoàn tất trong {elapsed:.2f} giây!")
    print(f"      Kích thước mô hình INT8 mới: {target_size_mb:.2f} MB")
    print(f"      Tỷ lệ nén giảm dung lượng:   {compression_ratio:.1f}%")

    # Kiểm tra tính toàn vẹn (Sanity Check)
    print(f"\n[4/4] Khởi tạo ONNX Runtime Session kiểm chuẩn mô hình INT8...")
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(target_onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
    
    input_names = [inp.name for inp in session.get_inputs()]
    output_names = [out.name for out in session.get_outputs()]
    print(f"      Inputs:  {input_names}")
    print(f"      Outputs: {output_names}")
    print(f"      [OK] ONNX Runtime nạp thành công mô hình INT8 trên CPUExecutionProvider!")

    print("\n" + "=" * 78)
    print("  KẾT QUẢ THỰC HIỆN THÀNH CÔNG RỰC RỠ!")
    print(f"  Mô hình INT8 sẵn sàng tại: {target_dir}")
    print("=" * 78)
    
    cache_root = define_cache_dir()
    jina_cache_dir = cache_root / "models--jinaai--jina-reranker-v2-base-multilingual"
    print(f"\n👉 LƯU Ý GIẢI PHÓNG DUNG LƯỢNG ĐĨA:")
    print(f"Bây giờ bạn có thể xóa thư mục mô hình FP32 cũ để giải phóng ~1.11 GB đĩa:")
    print(f'Remove-Item -Recurse -Force "{jina_cache_dir}"')
    print("=" * 78)


if __name__ == "__main__":
    quantize_reranker_to_int8()
