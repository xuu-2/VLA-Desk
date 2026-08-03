"""
TensorRT 推理后端。
提供 YOLOv8 TensorRT engine 的加载和推理能力。
如果没有安装 tensorrt，会优雅降级。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np


class TensorRTBackend:
    """封装 TensorRT engine 的加载和推理。"""

    def __init__(self, engine_path: str) -> None:
        self.engine_path = engine_path
        self.engine = None
        self.context = None
        self.stream = None
        self.host_inputs: List[np.ndarray] = []
        self.host_outputs: List[np.ndarray] = []
        self.cuda_inputs: List[int] = []
        self.cuda_outputs: List[int] = []
        self.bindings: List[int] = []
        self.input_shape: Optional[tuple] = None
        self.output_shape: Optional[tuple] = None

    def load(self) -> bool:
        """加载 TensorRT engine。如果 tensorrt 没装，返回 False。"""
        try:
            import tensorrt as trt
            import pycuda.driver as cuda
            import pycuda.autoinit  # noqa: F401
        except ImportError:
            print("[TensorRT] tensorrt 或 pycuda 未安装，跳过")
            return False

        if not Path(self.engine_path).exists():
            print(f"[TensorRT] engine 文件不存在: {self.engine_path}")
            return False

        import tensorrt as trt
        import pycuda.driver as cuda

        runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
        with open(self.engine_path, "rb") as f:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        if self.engine is None:
            print("[TensorRT] engine 反序列化失败")
            return False

        self.context = self.engine.create_execution_context()
        self.stream = cuda.Stream()

        # 解析输入输出
        for binding in self.engine:
            shape = self.engine.get_binding_shape(binding)
            dtype = trt.nptype(self.engine.get_binding_data_type(binding))
            size = int(np.prod(shape))
            host_mem = cuda.pagelocked_empty(size, dtype)
            cuda_mem = cuda.mem_alloc(host_mem.nbytes)
            self.bindings.append(int(cuda_mem))
            if self.engine.binding_is_input(binding):
                self.input_shape = tuple(shape)
                self.host_inputs.append(host_mem)
                self.cuda_inputs.append(cuda_mem)
            else:
                self.output_shape = tuple(shape)
                self.host_outputs.append(host_mem)
                self.cuda_outputs.append(cuda_mem)

        print(f"[TensorRT] engine 加载成功: {self.engine_path}")
        print(f"  input shape: {self.input_shape}")
        print(f"  output shape: {self.output_shape}")
        return True

    def infer(self, input_data: np.ndarray) -> List[np.ndarray]:
        """运行推理，返回输出列表。"""
        import pycuda.driver as cuda

        # 预处理输入到连续内存
        input_data = np.ascontiguousarray(input_data)
        np.copyto(self.host_inputs[0], input_data.ravel())
        cuda.memcpy_htod_async(self.cuda_inputs[0], self.host_inputs[0], self.stream)

        self.context.execute_async_v2(
            bindings=self.bindings,
            stream_handle=self.stream.handle,
        )

        outputs = []
        for i in range(len(self.host_outputs)):
            cuda.memcpy_dtoh_async(self.host_outputs[i], self.cuda_outputs[i], self.stream)
            outputs.append(self.host_outputs[i].reshape(self.output_shape))
        self.stream.synchronize()
        return outputs

    def release(self) -> None:
        for mem in self.cuda_inputs + self.cuda_outputs:
            if mem:
                mem.free()
        self.context = None
        self.engine = None

    @staticmethod
    def is_available() -> bool:
        try:
            import tensorrt  # noqa: F401
            import pycuda.driver  # noqa: F401
            return True
        except ImportError:
            return False
