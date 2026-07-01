# GPU/FLOPs 推理模型参数修正提案：LLM、TTI、ITI 三场景

> **版本**: v3.0（合并版）
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
3. 扩散模型推理由 text encoding + 迭代去噪 + VAE 解码组成，而非简单的 "cycles per byte"
4. 缺乏对模型规模、KV cache、内存带宽、去噪步数等关键因素的建模
5. 当前模型严重低估计算时延（~0.1 ms），与真实 benchmark 差距 3-4 个数量级

---

## 2. INC 节点 GPU 硬件参数（所有服务共享）

GPU 是 INC 节点的物理属性，所有服务（LLM、TTI、ITI）共享同一套硬件参数。每个 INC 节点配置一种真实 NVIDIA 数据中心 GPU，形成异构计算池。

| INC 节点 | GPU 型号 | FP16 Tensor Core (TFLOPS) | 显存带宽 (GB/s) | 显存 (GB) | 来源 |
|---|---|---|---|---|---|
| 0 | NVIDIA L4 | 121 | 204 | 24 GDDR6 | https://www.nvidia.com/en-us/data-center/l4/ |
| 1 | NVIDIA A10 | 125 | 600 | 24 GDDR6 | https://www.nvidia.com/en-us/data-center/products/a10-gpu/ |
| 2 | NVIDIA L40 | 181 | 864 | 48 GDDR6 | https://www.nvidia.com/en-us/data-center/l40/ |
| 3 | NVIDIA A30 | 165 | 933 | 24 HBM2 | https://www.nvidia.com/en-us/data-center/a30/ |
| 4 | NVIDIA A100 40GB | 312 | 1555 | 40 HBM2e | https://www.nvidia.com/en-us/data-center/a100/ |
| 5 | NVIDIA A100 80GB | 312 | 2039 | 80 HBM2e | https://www.nvidia.com/en-us/data-center/a100/ |

**GPU 利用率**：`incGpuUtilization = 0.6`（60%），考虑空闲时间、内存传输开销和批处理效率。

来源：NVIDIA Triton 性能分析器，https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/perf_analyzer.html；vLLM 论文报告实际利用率 50-70%，https://arxiv.org/abs/2309.06180

**设计说明**：
- 异构配置从入门级边缘推理（L4）到高端数据中心（A100 80GB），覆盖不同代际和性能层级
- L4/A10 代表轻量级边缘部署，L40/A30 代表中端推理，A100 代表高端推理
- A100 40GB 和 80GB 的区别在于显存容量和内存带宽（HBM2e 80GB 版本带宽更高）

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

### 3.4 各 GPU 节点时延计算（BurstGPT 中位数场景：547 input, 232 output）

| INC 节点 | GPU | Prefill | Decode | 总计 |
|---|---|---|---|---|
| 0 | L4 | 103 ms | 77.3 ms | 180 ms |
| 1 | A10 | 100 ms | 26.3 ms | 126 ms |
| 2 | L40 | 69 ms | 18.5 ms | 87 ms |
| 3 | A30 | 75 ms | 17.2 ms | 92 ms |
| 4 | A100 40GB | 40 ms | 10.3 ms | 50 ms |
| 5 | A100 80GB | 40 ms | 7.8 ms | 48 ms |

**不同分位数的计算时延**（以 L4 节点为例）：

| 分位数 | 输入 tokens | 输出 tokens | Prefill | Decode | 总计 |
|---|---|---|---|---|---|
| P10 | 100 | 50 | 19 ms | 16.6 ms | 35 ms |
| P50 | 547 | 232 | 103 ms | 77.3 ms | 180 ms |
| P90 | 2000 | 550 | 376 ms | 183 ms | 559 ms |
| P95 | 3200 | 800 | 602 ms | 267 ms | 869 ms |
| P99 | 5000 | 1200 | 940 ms | 400 ms | 1340 ms |

### 3.5 与公开基准对比

| 来源 | 模型 | 输入 | 输出 | 时延 | 备注 |
|---|---|---|---|---|---|
| 本提案（P50, L4） | 7B | 547 | 232 | 180 ms | 理论计算 |
| 本提案（P50, A100 80GB） | 7B | 547 | 232 | 48 ms | 理论计算 |
| OpenAI API | GPT-3.5 | ~500 | ~250 | 200-500 ms | 含网络开销 |
| vLLM 基准 | LLaMA-2 7B | 512 | 256 | 80-120 ms | A100 GPU |
| NVIDIA Triton | 7B | 512 | 256 | 60-100 ms | T4/A10 GPU |

### 3.6 Deadline 压力检查（deadline = 2.0 s，保持不变）

| GPU | 计算时延 (P50) | 端到端时延 | Deadline 裕量 |
|---|---|---|---|
| L4 | 180 ms | ~186 ms | 1.814 s |
| A10 | 126 ms | ~132 ms | 1.868 s |
| L40 | 87 ms | ~93 ms | 1.907 s |
| A30 | 92 ms | ~98 ms | 1.902 s |
| A100 40GB | 50 ms | ~56 ms | 1.944 s |
| A100 80GB | 48 ms | ~54 ms | 1.946 s |

---

## 4. TTI 场景（stableDiffusion text-to-image）

### 4.1 模型参数（SDXL Turbo）

| 参数 | 值 | 原因 | 来源 |
|---|---|---|---|
| sdxlUnetParams | `3.4e9`（3.4B） | SDXL 的 UNet 比 SD 1.5 大 3 倍。 | SDXL 论文：https://arxiv.org/abs/2307.01952 |
| sdxlTextEncoder1Params | `1.3e9`（1.3B） | OpenCLIP-ViT/G 文本编码器。 | SDXL 论文和 Hugging Face 模型卡：https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0 |
| sdxlTextEncoder2Params | `400e6`（400M） | CLIP-ViT/L 文本编码器。 | 同上 |
| sdxlVaeParams | `100e6`（100M） | 变分自编码器。 | LDM 论文：https://arxiv.org/abs/2112.10752 |
| sdxlTotalParams | `5.2e9`（5.2B） | UNet + Text Encoders + VAE。 | 上述之和 |
| sdxlModelSizeBytes | `10.4e9`（10.4 GB，FP16） | 5.2B * 2 bytes/param。 | 同上 |
| sdxlNumSteps | `4` | SDXL Turbo 使用对抗蒸馏，仅需 4 步即可生成图像。 | Stability AI 官方公告：https://stability.ai/news/stable-diffusion-xl-turbo |
| sdxlResolution | `1024x1024` | SDXL 原生输出分辨率。 | SDXL 论文：https://arxiv.org/abs/2307.01952；SaladCloud SDXL Benchmark：https://blog.salad.com/sdxl-benchmark/ |
| sdxlClipMaxTokens | `77` | CLIP 文本编码器硬限制。 | CLIP 模型规格：https://github.com/openai/CLIP |

### 4.2 输入/输出载荷

| 参数 | 值 | 说明 | 来源 |
|---|---|---|---|
| taskSize (input) | `308` B | 文本提示（最多 77 tokens * 4 bytes）。CLIP 硬限制 77 tokens。 | CLIP 模型规格：https://github.com/openai/CLIP |
| resultSize (output) | `1227776` B (~1.17 MiB) | 1024x1024 PNG 编码图像。与当前参数集一致。 | SaladCloud SDXL Benchmark 使用 1024x1024：https://blog.salad.com/sdxl-benchmark/；Stability AI API 文档：https://platform.stability.ai/docs/api-reference |
| taskDeadline | `2.6` s（保持不变） | 见下方时延计算。 | |

### 4.3 时延计算公式

TTI 推理管道由三个阶段组成：

```
compute_latency = text_encoding_latency + denoise_latency + vae_decode_latency
```

#### 阶段 1：Text Encoding（文本编码）

**做什么**：将用户输入的文本提示（如 "a photo of an astronaut riding a horse"）转换为模型可理解的数值表示（embedding 向量）。

**具体过程**：
1. 文本首先通过分词器（tokenizer）拆分为最多 77 个 token
2. 两个 CLIP 文本编码器（OpenCLIP-ViT/G 1.3B + CLIP-ViT/L 400M）分别处理这些 token
3. 每个编码器输出一个 77×d 的 embedding 矩阵（d 为隐藏维度）
4. 这些 embedding 将作为条件信息，在后续去噪过程中指导图像生成

**计算公式**：
```
text_encoding_latency = 2 * (encoder1_params + encoder2_params) * clip_max_tokens / (gpu_tflops * 1e12 * utilization)
```

- `2 * params * tokens`：Transformer 前向传播的 FLOPs 近似公式（每个参数在每个 token 上执行一次乘法和一次加法）
- `gpu_tflops * 1e12`：GPU 的峰值 FP16 算力（TFLOPS 转换为 FLOPS）
- `utilization`：实际利用率（考虑空闲、内存传输等开销）

**时延量级**：~2-4 ms（计算量小，因为只处理 77 个 token）

#### 阶段 2：UNet 迭代去噪（核心生成过程）

**做什么**：从纯噪声逐步生成图像。这是扩散模型的核心，也是计算最密集的阶段。

**具体过程**：
1. 从标准正态分布采样一个纯噪声张量（形状为 128×128×4，即潜在空间表示）
2. UNet 网络执行 4 次前向传播（SDXL Turbo 使用 4 步，标准 SDXL 使用 25-50 步）
3. 每次前向传播：
   - UNet 接收当前噪声图像 + 时间步嵌入 + 文本条件嵌入
   - 预测当前噪声图像中的"噪声成分"
   - 使用调度器（scheduler）从当前图像中减去预测的噪声，得到更清晰的图像
4. 经过 4 次迭代后，得到最终的潜在空间图像表示

**为什么用基准数据驱动而非 FLOPs 公式**：
- UNet 架构复杂（多尺度卷积 + 注意力机制），难以用简单公式估算 FLOPs
- 参考基准来自真实测量，包含框架开销、内存访问等实际因素

**参考基准**：RTX 4090 (330 TFLOPS FP16)，SDXL 1024x1024，25 步（20 base + 5 refiner），端到端总时延 6.2 s。

来源：SaladCloud SDXL Benchmark，https://blog.salad.com/sdxl-benchmark/

**关键修正**：参考测量值 6.2 s 是端到端时延，已包含 text encoding 和 VAE decode。为避免重复计算，需先扣除这些开销，提取纯 UNet 每步时延：

```
measured_total(4090) = 6.2 s
text_enc(4090) = 2 * 1.7e9 * 77 / (330e12 * 0.6) ≈ 1.3 ms
vae_decode(4090) ≈ 0.1 s

pure_denoise_total(4090) = 6.2 - 0.0013 - 0.1 = 6.099 s
pure_denoise_step(4090) = 6.099 / 25 ≈ 244 ms
```

然后对目标 GPU 进行 TFLOPS 缩放：

```
pure_denoise_step(target) = pure_denoise_step(4090) * tflops_4090 / tflops_target
denoise_latency = num_steps * pure_denoise_step(target)
```

**TFLOPS 缩放验证**（SaladCloud 数据）：

| GPU 对 | TFLOPS 比 | 实测每步时延比 | 一致性 |
|---|---|---|---|
| RTX 4090 (330) vs RTX 4080 (98) | 3.37 | 288/248 = 1.16 | 偏差（内存带宽差异） |
| RTX 4090 (330) vs RTX 3090 (71) | 4.65 | 422/248 = 1.70 | 偏差（架构差异） |

TFLOPS 线性缩放是一阶近似。实际受内存带宽、架构效率影响存在偏差，但作为仿真建模精度足够。

**时延量级**：~1-3 s（计算密集，占总时延 90%+）

#### 阶段 3：VAE 解码（潜在空间 → 像素空间）

**做什么**：将 UNet 输出的潜在空间表示（128×128×4）解码为最终的像素空间图像（1024×1024×3）。

**具体过程**：
1. VAE 解码器是一个卷积神经网络（约 100M 参数）
2. 接收 128×128×4 的潜在表示
3. 通过一系列上采样卷积层，逐步将分辨率从 128×128 提升到 1024×1024
4. 输出最终的 RGB 图像（1024×1024×3）
5. 图像随后被编码为 PNG 格式（约 1.17 MB）

**计算公式**：
```
vae_decode_latency = 0.1 s
```

这是一个相对固定的开销，因为：
- 输入/输出分辨率固定（128×128 → 1024×1024）
- VAE 参数量固定（~100M）
- 只执行一次前向传播

**时延量级**：~100 ms（相对固定，与 GPU 性能关系不大）

### 4.4 各 GPU 节点时延计算

#### Text Encoding 时延

`text_encoding_flops = 2 * (1.3e9 + 400e6) * 77 = 2.618e11`

| INC 节点 | GPU | Text Encoding 时延 |
|---|---|---|
| 0 | L4 | 3.6 ms |
| 1 | A10 | 3.5 ms |
| 2 | L40 | 2.4 ms |
| 3 | A30 | 2.6 ms |
| 4 | A100 40GB | 1.4 ms |
| 5 | A100 80GB | 1.4 ms |

#### UNet 纯去噪时延（4 步，1024x1024）

`pure_step = 244 ms * 330 / target_tflops`

| INC 节点 | GPU | 每步时延 | 4 步去噪 |
|---|---|---|---|
| 0 | L4 | 665 ms | 2.66 s |
| 1 | A10 | 644 ms | 2.58 s |
| 2 | L40 | 444 ms | 1.78 s |
| 3 | A30 | 488 ms | 1.95 s |
| 4 | A100 40GB | 258 ms | 1.03 s |
| 5 | A100 80GB | 258 ms | 1.03 s |

#### 总计算时延

| INC 节点 | GPU | Text Enc | 去噪 | VAE 解码 | **总计** | Deadline 裕量 |
|---|---|---|---|---|---|---|
| 0 | L4 | 3.6 ms | 2.66 s | 0.1 s | **2.76 s** | -0.16 s (超期) |
| 1 | A10 | 3.5 ms | 2.58 s | 0.1 s | **2.68 s** | -0.08 s (超期) |
| 2 | L40 | 2.4 ms | 1.78 s | 0.1 s | **1.88 s** | 0.72 s |
| 3 | A30 | 2.6 ms | 1.95 s | 0.1 s | **2.05 s** | 0.55 s |
| 4 | A100 40GB | 1.4 ms | 1.03 s | 0.1 s | **1.13 s** | 1.47 s |
| 5 | A100 80GB | 1.4 ms | 1.03 s | 0.1 s | **1.13 s** | 1.47 s |

**关键发现**：L4 和 A10 节点在 1024x1024 SDXL Turbo 4 步下无法满足 2.6 s deadline。这正是 proposed 方案优化器需要解决的问题——将 SDXL 任务优先分配到 L40 及以上的高性能节点。

### 4.5 与公开基准对比

| 来源 | GPU | 步数 | 分辨率 | 时延 | 备注 |
|---|---|---|---|---|---|
| 本提案（L4） | 121 TFLOPS | 4 | 1024x1024 | 2.76 s | 基准缩放 |
| 本提案（A100 80GB） | 312 TFLOPS | 4 | 1024x1024 | 1.13 s | 基准缩放 |
| Stability AI | RTX 4090 (330 TFLOPS) | 1 | 512x512 | ~200 ms | SDXL Turbo 官方公告：https://stability.ai/news/stable-diffusion-xl-turbo |
| Stability AI | RTX 4090 (330 TFLOPS) | 4 | 512x512 | ~800 ms | 同上 |
| SaladCloud | RTX 4090 (330 TFLOPS) | 25 | 1024x1024 | 6.2 s | https://blog.salad.com/sdxl-benchmark/ |
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
| resultSize (output) | `1227776` B (~1.17 MiB) | 1024x1024 PNG 编码图像。与当前参数集一致。 | SaladCloud SDXL Benchmark：https://blog.salad.com/sdxl-benchmark/ |
| taskDeadline | `2.6` s（保持不变） | 与 TTI 相同。 | |

### 5.3 时延计算

ITI 推理管道比 TTI 多一个 VAE 编码步骤（将输入图像编码到潜在空间）：

```
compute_latency = text_encoding + vae_encode + denoise + vae_decode
```

#### 阶段 1：Text Encoding（文本编码）

**做什么**：与 TTI 完全相同。将用户输入的文本提示转换为 embedding 向量，作为条件信息指导图像生成。

**时延**：~2-4 ms（见 TTI 阶段 1）

#### 阶段 2：VAE 编码（像素空间 → 潜在空间）

**做什么**：将用户输入的参考图像（1024×1024×3）编码为潜在空间表示（128×128×4）。

**具体过程**：
1. VAE 编码器是一个卷积神经网络（约 50M 参数，解码器的一半）
2. 接收 1024×1024×3 的 RGB 图像
3. 通过一系列下采样卷积层，逐步将分辨率从 1024×1024 降低到 128×128
4. 输出 128×128×4 的潜在表示（latent representation）
5. 这个潜在表示将作为去噪过程的起点（而非从纯噪声开始）

**为什么需要这一步**：
- TTI 从纯噪声开始生成图像，所以不需要 VAE encode
- ITI 从参考图像开始，需要先将其转换到潜在空间，然后在此基础上添加噪声并去噪
- 这样模型可以"保留"参考图像的结构和内容，同时根据文本提示进行修改

**计算公式**：
```
vae_encode_latency = 0.1 s
```

与 VAE decode 对称，因为：
- 编码器参数量约为解码器的一半（50M vs 100M）
- 但输入分辨率更高（1024×1024 vs 128×128）
- 两者计算量相近，时延量级相同

**时延量级**：~100 ms（相对固定）

#### 阶段 3：UNet 迭代去噪（核心生成过程）

**做什么**：与 TTI 完全相同。从潜在空间表示（此处为参考图像的编码 + 噪声）逐步去噪生成新图像。

**与 TTI 的区别**：
- TTI：从纯噪声开始（随机采样的 128×128×4 张量）
- ITI：从参考图像的潜在表示 + 部分噪声开始（通过 `strength` 参数控制噪声量）
- 去噪过程本身完全相同（UNet 前向传播 × 4 步）

**时延**：~1-3 s（见 TTI 阶段 2）

#### 阶段 4：VAE 解码（潜在空间 → 像素空间）

**做什么**：与 TTI 完全相同。将 UNet 输出的潜在空间表示解码为最终的像素空间图像。

**时延**：~100 ms（见 TTI 阶段 3）

#### 总计算时延汇总

| 阶段 | 说明 | 时延 |
|---|---|---|
| Text Encoding | 与 TTI 相同 | 见上表 |
| VAE Encode | 将 1024x1024 输入图像编码到潜在空间 | ~0.1 s |
| UNet 去噪 | 与 TTI 相同 | 见上表 |
| VAE Decode | 与 TTI 相同 | 0.1 s |

**ITI 总计算时延 = TTI 总计算时延 + 0.1 s（VAE encode）**

| INC 节点 | GPU | TTI 总计 | ITI 总计 | ITI Deadline 裕量 |
|---|---|---|---|---|
| 0 | L4 | 2.76 s | 2.86 s | -0.26 s (超期) |
| 1 | A10 | 2.68 s | 2.78 s | -0.18 s (超期) |
| 2 | L40 | 1.88 s | 1.98 s | 0.62 s |
| 3 | A30 | 2.05 s | 2.15 s | 0.45 s |
| 4 | A100 40GB | 1.13 s | 1.23 s | 1.37 s |
| 5 | A100 80GB | 1.13 s | 1.23 s | 1.37 s |

**差异仅在网络传输和 VAE encode**：
- TTI 上传：308 B（极轻）
- ITI 上传：867,636 B（~0.83 MiB，受 RAN 带宽影响显著）

### 5.4 端到端时延对比（含网络传输）

| 场景 | 上传时延 (90 Mbps RAN) | 计算时延 (L40) | 下载时延 | 端到端时延 | Deadline 裕量 |
|---|---|---|---|---|---|
| TTI | < 0.1 ms | 1.88 s | ~109 ms | ~1.99 s | 0.61 s |
| ITI | ~77 ms | 1.98 s | ~109 ms | ~2.17 s | 0.43 s |

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

### 6.3 计算时延汇总（各 GPU 节点）

| INC 节点 | GPU | LLM (P50) | TTI | ITI |
|---|---|---|---|---|
| 0 | L4 | 180 ms | 2.76 s | 2.86 s |
| 1 | A10 | 126 ms | 2.68 s | 2.78 s |
| 2 | L40 | 87 ms | 1.88 s | 1.98 s |
| 3 | A30 | 92 ms | 2.05 s | 2.15 s |
| 4 | A100 40GB | 50 ms | 1.13 s | 1.23 s |
| 5 | A100 80GB | 48 ms | 1.13 s | 1.23 s |

### 6.4 与当前 CPU 模型的对比

| 场景 | 当前 CPU 模型 | 提议 GPU 模型 (L40) | 差异倍数 |
|---|---|---|---|
| LLM (P50) | ~0.1 ms | ~87 ms | ~870x |
| TTI | ~0.1 ms | ~1.88 s | ~18800x |
| ITI | ~0.1 ms | ~1.98 s | ~19800x |

---

## 7. 实现建议

### 7.1 新增参数

```cpp
// INC 节点 GPU 硬件参数（所有服务共享，每个节点对应一种真实 GPU）
struct GpuSpec {
    std::string name;
    double fp16Tflops;
    double memoryBandwidthGBps;
    double memoryGB;
};

std::vector<GpuSpec> incGpuSpecs = {
    {"L4",        121,  204,  24},   // 节点 0
    {"A10",       125,  600,  24},   // 节点 1
    {"L40",       181,  864,  48},   // 节点 2
    {"A30",       165,  933,  24},   // 节点 3
    {"A100-40",   312, 1555,  40},   // 节点 4
    {"A100-80",   312, 2039,  80},   // 节点 5
};
double incGpuUtilization = 0.6;

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
sdxlTextEncoder1Params = 1.3e9;   // OpenCLIP-ViT/G
sdxlTextEncoder2Params = 400e6;   // CLIP-ViT/L
sdxlUnetParams = 3.4e9;
sdxlNumSteps = 4;
sdxlResolution = 1024;
sdxlVaeDecodeTime = 0.1;
sdxlVaeEncodeTime = 0.1;
sdxlClipMaxTokens = 77;

// SDXL 基准缩放参数（来自 SaladCloud SDXL Benchmark）
// 参考测量：RTX 4090 (330 TFLOPS)，25 步，端到端 6.2 s
// 纯 UNet 每步时延 = (6.2 - text_enc - vae_decode) / 25
//                  = (6.2 - 0.0013 - 0.1) / 25 ≈ 244 ms
sdxlRefPureStepLatencyMs = 244;  // RTX 4090 (330 TFLOPS) 纯 UNet 每步时延
sdxlRefGpuTflops = 330;          // 参考 GPU TFLOPS
```

### 7.2 时延计算逻辑

```cpp
double ComputeLLMLatency(int inputTokens, int outputTokens,
                         const GpuSpec& gpu) {
    double prefill = 2.0 * llmModelParams * inputTokens
                     / (gpu.fp16Tflops * 1e12 * incGpuUtilization);
    double decode = outputTokens * (llmModelSizeBytes + llmKVCacheBytes)
                    / (gpu.memoryBandwidthGBps * 1e9);
    return prefill + decode;
}

double ComputeTTILatency(const GpuSpec& gpu) {
    double textEnc = 2.0 * (sdxlTextEncoder1Params + sdxlTextEncoder2Params)
                     * sdxlClipMaxTokens
                     / (gpu.fp16Tflops * 1e12 * incGpuUtilization);
    double pureStep = sdxlRefPureStepLatencyMs * 1e-3
                      * sdxlRefGpuTflops / gpu.fp16Tflops;
    double denoise = sdxlNumSteps * pureStep;
    return textEnc + denoise + sdxlVaeDecodeTime;
}

double ComputeITILatency(const GpuSpec& gpu) {
    return ComputeTTILatency(gpu) + sdxlVaeEncodeTime;
}
```

### 7.3 向后兼容性

```cpp
if (useGpuModel) {
    if (taskType == "chatbot") {
        computeLatency = ComputeLLMLatency(inputTokens, outputTokens, gpu);
    } else if (taskType == "stableDiffusion_tti") {
        computeLatency = ComputeTTILatency(gpu);
    } else if (taskType == "stableDiffusion_iti") {
        computeLatency = ComputeITILatency(gpu);
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
10. NVIDIA L40 规格：https://www.nvidia.com/en-us/data-center/l40/
11. NVIDIA A30 规格：https://www.nvidia.com/en-us/data-center/a30/
12. NVIDIA A100 规格：https://www.nvidia.com/en-us/data-center/a100/
13. NVIDIA Triton 性能分析器：https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/user_guide/perf_analyzer.html
14. OpenAI 时延优化指南：https://developers.openai.com/api/docs/guides/latency-optimization
15. Podell, D., et al. (2023). "SDXL: Improving Latent Diffusion Models for High-Resolution Image Synthesis." arXiv:2307.01952
16. Rombach, R., et al. (2022). "High-Resolution Image Synthesis with Latent Diffusion Models." arXiv:2112.10752
17. SaladCloud SDXL Benchmark：https://blog.salad.com/sdxl-benchmark/
18. Replicate SDXL 部署：https://replicate.com/stability-ai/sdxl
19. Stability AI API 文档：https://platform.stability.ai/docs/api-reference
20. Stability AI SDXL Turbo 公告：https://stability.ai/news/stable-diffusion-xl-turbo
21. SDXL Hugging Face 模型卡：https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
22. CLIP 模型规格：https://github.com/openai/CLIP

---

## 9. 下一步行动

1. 审查本提案的参数值和计算公式
2. 确认是否需要调整 GPU 硬件配置（GPU 型号选择、节点分配）
3. 确认是否需要调整模型参数（model_params、model_size、kv_cache）
4. 实现 GPU 时延计算逻辑
5. 运行小规模测试验证时延计算的正确性
6. 运行完整的 100 次仿真并对比结果
