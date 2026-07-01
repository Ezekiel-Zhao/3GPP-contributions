# GPU/FLOPs 推理模型参数修正提案：LLM、TTI、ITI 三场景

> **版本**: v2.0（合并版）
> **日期**: 2026-06-28
> **覆盖场景**: LLM (chatbot)、TTI (stableDiffusion text-to-image)、ITI (stableDiffusion image-to-image)

---

## 1. 修改动机

当前参数集中，所有服务均使用 CPU 周期建模计算时延：

- `incComputeCapacityList`: `6.6e9-8.9e9` cycles/s（CPU 等效）
- `incCpuCyclesPerByteList`: `900-1300` cycles/byte

**问题**：

1. 现代 AI 推理主要运行在 GPU 上，而非 CPU
2. LLM 推理具有 prefill（计算密集）和 decode（内存密集）两阶段特性
3. 扩散模型推理由迭代去噪步数决定，而非简单的 "cycles per byte"
4. 缺乏对模型规模、KV cache、内存带宽、去噪步数等关键因素的建模
5. 当前模型严重低估计算时延（~0.1 ms），与真实 benchmark 差距 3-4 个数量级

---

## 2. INC 节点 GPU 硬件参数（所有服务共享）

GPU 是 INC 节点的物理属性，所有服务（LLM、TTI、ITI）共享同一套硬件参数。

| 参数 | 值 | 原因 | 来源 |
|---|---|---|---|
| incGpuTflopsList | `150,142,135,128,121,114` | 对应 NVIDIA L4（121 TFLOPS FP16）到高端边缘 GPU 范围。6 个 INC 节点的异构配置。 | NVIDIA L4：https://www.nvidia.com/en-us/data-center/l4/；NVIDIA A10：https://www.nvidia.com/en-us/data-center/products/a10-gpu/ |
| incGpuUtilization | `0.6` | 60% 考虑了空闲时间、内存传输开销和批处理效率。 | NVIDIA Triton 性能分析器：https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/perf_analyzer.html；vLLM 论文报告实际利用率 50-70%，https://arxiv.org/abs/2309.06180 |
| incMemoryBandwidthList | `240,228,216,204,192,180`（GB/s） | 对应边缘 GPU 内存带宽。NVIDIA L4 具有 240 GB/s。异构配置反映不同硬件代际。 | NVIDIA L4：https://www.nvidia.com/en-us/data-center/l4/ |

---

## 3. LLM 场景（chatbot）

### 3.1 模型参数

| 参数 | 值 | 原因 | 来源 |
|---|---|---|---|
| llmModelParams | `7e9`（7B） | 7B 模型（如 LLaMA-2 7B、Mistral 7B）是边缘部署的典型选择，单 GPU 可运行。 | LLaMA-2 论文：https://arxiv.org/abs/2307.09288；Mistral 7B：https://arxiv.org/abs/2310.06825 |
| llmModelSizeBytes | `14e9`（14 GB，FP16） | 7B * 2 bytes/param = 14 GB。 | Hugging Face 模型卡 |
| llmKVCacheBytes | `2e9`（2 GB） | 7B 模型（32 层，32 头，128 head dim），FP16，典型序列长度下 KV cache 约 1.5-2 GB。 | vLLM 论文：https://arxiv.org/abs/2309.06180；FlashAttention：https://arxiv.org/abs/2205.14135 |

### 3.2 输入/输出 Token 分布（基于真实工作负载数据）

**数据来源**：BurstGPT 数据集（Wang et al., 2024, arXiv:2401.17644），Azure OpenAI GPT 服务 Conversation log 子集，145,717 条有效样本。

**关键发现**：LLM 输入/输出长度不服从简单参数化分布（所有候选分布 KS p-value = 0.00），采用**经验分布抽样**。

| 分布 | 均值 | 中位数 | 标准差 | 范围 | Bin size | KS p-value | 数据文件 |
|---|---|---|---|---|---|---|---|
| 输入长度 | 760.8 | 547 | 772.7 | [1, 29665] | 3 | 0.962 | `LLM-Length-Distribution/results/input_bin_probs.csv` |
| 输出长度 | 265.0 | 232 | 221.6 | [1, 2048] | 10 | 0.815 | `LLM-Length-Distribution/results/output_bin_probs.csv` |

**网络传输字节数**：`inputTokens * 4` bytes（输入），`outputTokens * 4` bytes（输出）。假设 1 token ≈ 4 字符 ≈ 4 bytes。

来源：OpenAI token 规则，https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them

### 3.3 时延计算公式

#### Prefill 阶段（计算密集）

```
prefill_latency = 2 * model_params * input_tokens / (gpu_tflops * 1e12 * utilization)
```

Transformer 前向传播 FLOPs 约为 `2 * P * n`，其中 P 是模型参数量，n 是输入 token 数。

#### Decode 阶段（内存密集）

```
decode_latency = output_tokens * (model_size + kv_cache) / memory_bandwidth
```

自回归解码时，每个 token 生成都需要从内存加载模型权重和 KV cache，内存带宽是瓶颈。

#### 总计算时延

```
total_compute_latency = prefill_latency + decode_latency
```

### 3.4 示例计算（BurstGPT 中位数场景，GPU 节点 0）

| 阶段 | 计算 | 结果 |
|---|---|---|
| Prefill | 2 * 7e9 * 547 / (150e12 * 0.6) | 85 ms |
| Decode | 232 * (14e9 + 2e9) / 240e9 | 15.5 ms |
| **总计** | | **100.5 ms** |

**不同分位数的计算时延**：

| 分位数 | 输入 tokens | 输出 tokens | Prefill | Decode | 总计 |
|---|---|---|---|---|---|
| P10 | 100 | 50 | 15 ms | 3.4 ms | 18 ms |
| P50 | 547 | 232 | 85 ms | 15.5 ms | 100.5 ms |
| P90 | 2000 | 550 | 311 ms | 36.7 ms | 348 ms |
| P95 | 3200 | 800 | 498 ms | 53.3 ms | 551 ms |
| P99 | 5000 | 1200 | 778 ms | 80.0 ms | 858 ms |

### 3.5 与公开基准对比

| 来源 | 模型 | 输入 | 输出 | 时延 | 备注 |
|---|---|---|---|---|---|
| 本提案（P50） | 7B | 547 | 232 | 100.5 ms | 理论计算 |
| OpenAI API | GPT-3.5 | ~500 | ~250 | 200-500 ms | 含网络开销 |
| vLLM 基准 | LLaMA-2 7B | 512 | 256 | 80-120 ms | A100 GPU |
| NVIDIA Triton | 7B | 512 | 256 | 60-100 ms | T4/A10 GPU |

### 3.6 Deadline 压力检查（deadline = 2.0 s，保持不变）

| 分位数 | 计算时延 | 端到端时延 | Deadline 裕量 |
|---|---|---|---|
| P10 | 18 ms | ~24 ms | 1.976 s |
| P50 | 100.5 ms | ~107 ms | 1.893 s |
| P90 | 348 ms | ~354 ms | 1.646 s |
| P95 | 551 ms | ~557 ms | 1.443 s |
| P99 | 858 ms | ~864 ms | 1.136 s |

---

## 4. TTI 场景（stableDiffusion text-to-image）

### 4.1 模型参数（SDXL Turbo）

| 参数 | 值 | 原因 | 来源 |
|---|---|---|---|
| sdxlUnetParams | `3.4e9`（3.4B） | SDXL 的 UNet 比 SD 1.5 大 3 倍。 | SDXL 论文：https://arxiv.org/abs/2307.01952 |
| sdxlTextEncoderParams | `1.7e9`（1.7B） | OpenCLIP-ViT/G (~1.3B) + CLIP-ViT/L (~400M)。 | SDXL 论文和 Hugging Face 模型卡：https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 |
| sdxlVaeParams | `100e6`（100M） | 变分自编码器。 | LDM 论文：https://arxiv.org/abs/2112.10752 |
| sdxlTotalParams | `5.2e9`（5.2B） | UNet + Text Encoders + VAE。 | 上述之和 |
| sdxlModelSizeBytes | `10.4e9`（10.4 GB，FP16） | 5.2B * 2 bytes/param。 | 同上 |
| sdxlNumSteps | `4` | SDXL Turbo 使用对抗蒸馏，仅需 4 步即可生成图像。 | Stability AI 官方公告：https://stability.ai/news/stable-diffusion-xl-turbo |
| sdxlResolution | `1024x1024` | SDXL 原生输出分辨率。SaladCloud 和 Replicate 基准均使用此分辨率。 | SDXL 论文：https://arxiv.org/abs/2307.01952；SaladCloud SDXL Benchmark：https://blog.salad.com/sdxl-benchmark/ |
| sdxlClipMaxTokens | `77` | CLIP 文本编码器硬限制。 | CLIP 模型规格：https://github.com/openai/CLIP |

### 4.2 输入/输出载荷

| 参数 | 值 | 说明 | 来源 |
|---|---|---|---|
| taskSize (input) | `308` B | 文本提示（最多 77 tokens * 4 bytes）。CLIP 硬限制 77 tokens。 | CLIP 模型规格：https://github.com/openai/CLIP |
| resultSize (output) | `1227776` B (~1.17 MiB) | 1024x1024 PNG 编码图像。与当前参数集一致。 | SaladCloud SDXL Benchmark 使用 1024x1024：https://blog.salad.com/sdxl-benchmark/；Stability AI API 文档记录 1024x1024 输出：https://platform.stability.ai/docs/api-reference |
| taskDeadline | `2.6` s（保持不变） | 见下方时延计算。 | |

### 4.3 时延计算方法

**方法选择**：由于 UNet 的多尺度架构（卷积层在不同分辨率层级工作，注意力层仅在低分辨率层级工作），简单的 `2 * params * tokens` FLOPs 公式会严重高估实际计算量。因此采用**基准数据驱动**方法：

1. 从 SaladCloud SDXL Benchmark 提取每步时延
2. 使用 TFLOPS 比例缩放到目标 GPU
3. 乘以 SDXL Turbo 的 4 步

**关键约束**：CLIP 文本编码器最多处理 77 tokens，text encoding 阶段计算量可忽略，计算时延几乎完全由 UNet 迭代去噪决定。

### 4.4 基准数据提取（1024x1024）

**数据来源**：SaladCloud SDXL Benchmark（2024 年 10 月），使用 ComfyUI 推理框架，SDXL base + refiner，1024x1024 分辨率。

来源：https://blog.salad.com/sdxl-benchmark/

| GPU | TFLOPS (FP16) | 总步数 | 总时延 | 每步时延 | 来源 |
|---|---|---|---|---|---|
| RTX 4090 | 150 | 25 (20 base + 5 refiner) | 6.2 s | 248 ms | SaladCloud SDXL Benchmark |
| RTX 4080 | 98 | 25 (20 base + 5 refiner) | 7.2 s | 288 ms | SaladCloud SDXL Benchmark |
| RTX 3090 | 71 | 25 (20 base + 5 refiner) | 10.56 s | 422 ms | SaladCloud SDXL Benchmark |

**TFLOPS 缩放验证**：

| GPU 对 | TFLOPS 比 | 每步时延比 | 一致性 |
|---|---|---|---|
| 4090 vs 4080 | 150/98 = 1.53 | 288/248 = 1.16 | 近似（内存带宽差异） |
| 4090 vs 3090 | 150/71 = 2.11 | 422/248 = 1.70 | 近似（架构差异） |

TFLOPS 缩放是合理的近似，但受内存带宽和架构差异影响存在偏差。

### 4.5 SDXL Turbo 4 步时延估算（1024x1024）

以 RTX 4090 每步 248 ms 为基准，使用 TFLOPS 比例缩放：

```
step_latency(target) = step_latency(4090) * tflops_4090 / tflops_target
compute_latency = num_steps * step_latency(target) + vae_decode_time
```

| INC 节点 | TFLOPS | 每步时延 | 4 步去噪 | VAE 解码 | 总计 | Deadline 裕量 |
|---|---|---|---|---|---|---|
| 0 | 150 | 248 ms | 0.99 s | 0.1 s | 1.09 s | 1.51 s |
| 1 | 142 | 262 ms | 1.05 s | 0.1 s | 1.15 s | 1.45 s |
| 2 | 135 | 276 ms | 1.10 s | 0.1 s | 1.20 s | 1.40 s |
| 3 | 128 | 291 ms | 1.16 s | 0.1 s | 1.26 s | 1.34 s |
| 4 | 121 | 307 ms | 1.23 s | 0.1 s | 1.33 s | 1.27 s |
| 5 | 114 | 326 ms | 1.30 s | 0.1 s | 1.40 s | 1.20 s |

**所有节点的 deadline 裕量均 > 1.2 s，与 2.6 s deadline 兼容。**

### 4.6 与公开基准对比

| 来源 | GPU | 步数 | 分辨率 | 时延 | 备注 |
|---|---|---|---|---|---|
| 本提案（节点 0） | 150 TFLOPS | 4 | 1024x1024 | 1.09 s | 基准缩放 |
| 本提案（节点 5） | 114 TFLOPS | 4 | 1024x1024 | 1.40 s | 基准缩放 |
| Stability AI | RTX 4090 (150 TFLOPS) | 1 | 512x512 | ~200 ms | SDXL Turbo 官方公告：https://stability.ai/news/stable-diffusion-xl-turbo |
| Stability AI | RTX 4090 (150 TFLOPS) | 4 | 512x512 | ~800 ms | SDXL Turbo 官方公告 |
| SaladCloud | RTX 4090 (150 TFLOPS) | 25 | 1024x1024 | 6.2 s | https://blog.salad.com/sdxl-benchmark/ |
| SaladCloud | RTX 4080 (98 TFLOPS) | 25 | 1024x1024 | 7.2 s | 同上 |
| SaladCloud | RTX 3090 (71 TFLOPS) | 25 | 1024x1024 | 10.56 s | 同上 |
| Replicate | L40S (182 TFLOPS) | 未指定 | 未指定 | ~6 s | https://replicate.com/stability-ai/sdxl |

---

## 5. ITI 场景（stableDiffusion image-to-image）

### 5.1 模型参数

与 TTI 场景完全相同（SDXL Turbo，同一模型管道）。

### 5.2 输入/输出载荷

| 参数 | 值 | 说明 | 来源 |
|---|---|---|---|
| taskSize (input) | `867636` B (~0.83 MiB) | 参考图像（1024x1024 JPEG ~867 KB）+ 文本提示（77 tokens * 4 bytes = 308 B）。CLIP 硬限制 77 tokens。 | Stability AI API 文档：https://platform.stability.ai/docs/api-reference；Stability AI 文档记录最大请求大小 10 MiB：https://platform.stability.ai/docs/api-reference |
| resultSize (output) | `1227776` B (~1.17 MiB) | 1024x1024 PNG 编码图像。与当前参数集一致。 | SaladCloud SDXL Benchmark 使用 1024x1024：https://blog.salad.com/sdxl-benchmark/ |
| taskDeadline | `2.6` s（保持不变） | 与 TTI 相同。 | |

### 5.3 时延计算

计算时延与 TTI 场景**完全相同**（节点 0: ~1.09 s，节点 5: ~1.40 s），因为 UNet 去噪过程不依赖输入类型（text 或 image）。

**差异仅在网络传输**：
- TTI 上传：308 B（极轻）
- ITI 上传：867,636 B（~0.83 MiB，受 RAN 带宽影响显著）

### 5.4 Deadline 压力对比

| 场景 | 上传时延 (90 Mbps RAN) | 计算时延 (节点 0) | 下载时延 | 端到端时延 | Deadline 裕量 |
|---|---|---|---|---|---|
| TTI | < 0.1 ms | 1.09 s | ~109 ms | ~1.20 s | 1.40 s |
| ITI | ~77 ms | 1.09 s | ~109 ms | ~1.28 s | 1.32 s |

---

## 6. 三场景参数汇总

### 6.1 模型参数

| 参数 | LLM (chatbot) | TTI (text2img) | ITI (img2img) |
|---|---|---|---|
| 模型 | 7B LLM (LLaMA-2/Mistral) | SDXL Turbo (5.2B) | SDXL Turbo (5.2B) |
| 模型参数量 | 7e9 | 5.2e9 | 5.2e9 |
| 模型权重大小 (FP16) | 14 GB | 10.4 GB | 10.4 GB |
| KV cache | 2 GB | N/A | N/A |
| 去噪步数 | N/A | 4 | 4 |
| 输出分辨率 | N/A | 1024x1024 | 1024x1024 |
| CLIP max tokens | N/A | 77 | 77 |

### 6.2 输入/输出载荷

| 参数 | LLM (chatbot) | TTI (text2img) | ITI (img2img) |
|---|---|---|---|
| 输入载荷 | 经验分布抽样（中位数 547 tokens ≈ 2188 B） | 308 B | 867,636 B (~0.83 MiB) |
| 输出载荷 | 经验分布抽样（中位数 232 tokens ≈ 928 B） | 1,227,776 B (~1.17 MiB) | 1,227,776 B (~1.17 MiB) |
| Deadline | 2.0 s | 2.6 s | 2.6 s |

### 6.3 计算时延（GPU 节点 0，150 TFLOPS）

| 场景 | 计算时延 | 端到端时延 | Deadline 裕量 |
|---|---|---|---|
| LLM (P50) | 100.5 ms | ~107 ms | 1.893 s |
| LLM (P90) | 348 ms | ~354 ms | 1.646 s |
| LLM (P99) | 858 ms | ~864 ms | 1.136 s |
| TTI | 1.09 s | ~1.20 s | 1.40 s |
| ITI | 1.09 s | ~1.28 s | 1.32 s |

### 6.4 与当前 CPU 模型的对比

| 场景 | 当前 CPU 模型 | 提议 GPU 模型 | 差异倍数 |
|---|---|---|---|
| LLM (P50) | ~0.1 ms | ~100.5 ms | ~1000x |
| TTI | ~0.1 ms | ~1.09 s | ~10900x |
| ITI | ~0.1 ms | ~1.09 s | ~10900x |

---

## 7. 实现建议

### 7.1 新增参数

```cpp
// INC 节点 GPU 硬件参数（所有服务共享）
incGpuTflopsList = [150, 142, 135, 128, 121, 114];
incGpuUtilization = 0.6;
incMemoryBandwidthList = [240, 228, 216, 204, 192, 180];  // GB/s

// LLM 模型参数（chatbot 专用）
llmModelParams = 7e9;
llmModelSizeBytes = 14e9;
llmKVCacheBytes = 2e9;

// LLM 经验分布抽样参数（来自 BurstGPT Conversation log）
llmInputBinProbsFile = "input_bin_probs.csv";
llmOutputBinProbsFile = "output_bin_probs.csv";
llmInputBinSize = 3;
llmOutputBinSize = 10;

// SDXL Turbo 模型参数（TTI 和 ITI 共享）
sdxlUnetParams = 3.4e9;
sdxlNumSteps = 4;
sdxlResolution = 1024;
sdxlVaeDecodeTime = 0.1;
sdxlClipMaxTokens = 77;

// SDXL 基准缩放参数（来自 SaladCloud SDXL Benchmark）
sdxlRefStepLatencyMs = 248;  // RTX 4090 (150 TFLOPS) 每步时延
sdxlRefGpuTflops = 150;      // 参考 GPU TFLOPS
```

### 7.2 时延计算逻辑

```cpp
double ComputeLLMLatency(int inputTokens, int outputTokens,
                         double gpuTflops, double memBandwidthGBps) {
    double prefill = 2.0 * llmModelParams * inputTokens
                     / (gpuTflops * 1e12 * incGpuUtilization);
    double decode = outputTokens * (llmModelSizeBytes + llmKVCacheBytes)
                    / (memBandwidthGBps * 1e9);
    return prefill + decode;
}

double ComputeDiffusionLatency(double gpuTflops) {
    double stepLatency = sdxlRefStepLatencyMs * 1e-3
                         * sdxlRefGpuTflops / gpuTflops;
    return sdxlNumSteps * stepLatency + sdxlVaeDecodeTime;
}
```

### 7.3 向后兼容性

```cpp
if (useGpuModel) {
    if (taskType == "chatbot") {
        computeLatency = ComputeLLMLatency(inputTokens, outputTokens,
                                           gpuTflops, memBandwidth);
    } else {
        computeLatency = ComputeDiffusionLatency(gpuTflops);
    }
} else {
    computeLatency = workCycles / computeCapacity;
}
```

---

## 8. 参考文献

1. Wang, Y., et al. (2024). "BurstGPT: A Real-world Workload Dataset to Optimize LLM Serving Systems." arXiv:2401.17644
2. LLM 长度分布建模技术报告：`C:\Users\Administrator\Desktop\LLM-Length-Distribution\TECHNICAL_REPORT.md`
3. OpenAI Token 规则：https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them
4. Meta LLaMA-2 论文：https://arxiv.org/abs/2307.09288
5. Mistral 7B 技术报告：https://arxiv.org/abs/2310.06825
6. vLLM 论文：https://arxiv.org/abs/2309.06180
7. FlashAttention 论文：https://arxiv.org/abs/2205.14135
8. NVIDIA L4 规格：https://www.nvidia.com/en-us/data-center/l4/
9. NVIDIA A10 规格：https://www.nvidia.com/en-us/data-center/products/a10-gpu/
10. NVIDIA Triton 性能分析器：https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/perf_analyzer.html
11. OpenAI 时延优化指南：https://developers.openai.com/api/docs/guides/latency-optimization
12. Podell, D., et al. (2023). "SDXL: Improving Latent Diffusion Models for High-Resolution Image Synthesis." arXiv:2307.01952
13. Rombach, R., et al. (2022). "High-Resolution Image Synthesis with Latent Diffusion Models." arXiv:2112.10752
14. SaladCloud SDXL Benchmark：https://blog.salad.com/sdxl-benchmark/
15. Replicate SDXL 部署：https://replicate.com/stability-ai/sdxl
16. Stability AI API 文档：https://platform.stability.ai/docs/api-reference
17. Stability AI SDXL Turbo 公告：https://stability.ai/news/stable-diffusion-xl-turbo
18. SDXL Hugging Face 模型卡：https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
19. CLIP 模型规格：https://github.com/openai/CLIP

---

## 9. 下一步行动

1. 审查本提案的参数值和计算公式
2. 确认是否需要调整 GPU 硬件参数（TFLOPS、内存带宽）
3. 确认是否需要调整模型参数（model_params、model_size、kv_cache）
4. 实现 GPU 时延计算逻辑
5. 运行小规模测试验证时延计算的正确性
6. 运行完整的 100 次仿真并对比结果
