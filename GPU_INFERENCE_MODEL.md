# INC 节点 GPU 推理时延建模方案

> **版本**: v1.0
> **日期**: 2026-07-03

---

## 1. 为什么要改？

当前 NS-3 仿真中，INC 节点的计算时延用 CPU 周期建模（`cycles/byte`），存在两个问题：

1. **不真实**：现代 AI 推理跑在 GPU 上，不是 CPU
2. **差距大**：CPU 模型算出 ~0.1 ms，真实 GPU 推理是几十 ms 到几秒

---

## 2. 三种 GPU

| INC 节点 | GPU | 架构 | FP16 算力 (TFLOPS) | 显存带宽 (GB/s) | 显存 (GB) | 支持 MIG |
|---|---|---|---|---|---|---|
| 0 | V100 | Volta | 125 | 900 | 32 | 是 (最多 4 实例) |
| 1 | A10 | Ampere | 125 | 600 | 24 | 是 (最多 4 实例) |
| 2 | A100 80GB | Ampere | 312 | 2039 | 80 | 是 (最多 7 实例) |

---

## 3. MIG 切分模型

假设三种 GPU 均支持 MIG（Multi-Instance GPU），可以将一块物理 GPU 硬件切分为多个独立实例。

**核心特性**：
- 每个 MIG 实例拥有**独立的算力、带宽、显存**，互不干扰
- 假设支持任意比例切分（实际中A100 支持 1/7, 2/7, 3/7, 7/7 四种档位）

**切分公式**：

```
MIG 实例算力 = 物理 GPU 算力 × α
MIG 实例带宽 = 物理 GPU 带宽 × α
MIG 实例显存 = 物理 GPU 显存 × α
```

其中 α 为切分比例（0 < α ≤ 1）。

---

## 4. 三种任务的时延模型

### 4.1 LLM（Chatbot）

7B 模型（如 LLaMA-2 7B），分两阶段：

```
LLM 时延 = Prefill 时延 + Decode 时延
```

**Prefill（计算密集）**：一次性处理所有输入 token

```
Prefill = 2 × 参数量 × 输入token数 / (MIG算力 × 0.95)
```

- `2 × P × n`：每个参数对每个 token 做 1 次乘法 + 1 次加法 = 2 FLOPs
- `0.95`：框架开销系数（CUDA kernel launch 等）

**Decode（访存密集）**：逐 token 生成，每个 token 都要加载全部模型权重

```
Decode = 输出token数 × (模型权重 + KV cache) / (MIG带宽 × 0.95)
```

- 瓶颈在**显存带宽**，不在算力

**各 GPU 时延**（547 input, 232 output）：

| GPU | Prefill | Decode | 总计 |
|---|---|---|---|
| V100 | 64.7 ms | 4340 ms | **4405 ms (4.4 s)** |
| A10 | 64.7 ms | 6510 ms | **6575 ms (6.6 s)** |
| A100 80GB | 25.9 ms | 1916 ms | **1942 ms (1.9 s)** |

**计算示例（A100）**：
```
Prefill = 2 × 7e9 × 547 / (312e12 × 0.95) = 25.9 ms
Decode = 232 × 16e9 / (2039e9 × 0.95) = 1916 ms
Total = 25.9 + 1916 = 1942 ms
```

---

### 4.2 TTI（Text-to-Image）

SDXL 模型，1024×1024 分辨率，20-25 步去噪。

**直接使用实测数据**：

| GPU | 实测端到端时延 |
|---|---|
| V100 | **8.5 s** |
| A10 | **6.8 s** |
| A100 80GB | **4.2 s** |

---

### 4.3 ITI（Image-to-Image）

与 TTI 相同，多一步 VAE 编码（+0.1 s）：

| GPU | TTI | ITI |
|---|---|---|
| V100 | 8.5 s | **8.6 s** |
| A10 | 6.8 s | **6.9 s** |
| A100 80GB | 4.2 s | **4.3 s** |

---

## 5. 汇总

| INC 节点 | GPU | LLM (P50) | TTI | ITI |
|---|---|---|---|---|
| 0 | V100 | 4.4 s | 8.50 s | 8.60 s |
| 1 | A10 | 6.6 s | 6.80 s | 6.90 s |
| 2 | A100 80GB | 1.9 s | 4.20 s | 4.30 s |

---

## 6. 代码实现

```cpp
struct PhysicalGpuSpec {
    std::string name;
    double fp16Tflops;
    double memoryBandwidthGBps;
    double memoryGB;
    bool supportsMig;
};

std::vector<PhysicalGpuSpec> physicalGpuCatalog = {
    {"V100",      125,  900,  32, true},
    {"A10",       125,  600,  24, true},
    {"A100-80",   312, 2039,  80, true},
};

struct MigInstance {
    uint32_t physicalGpuIndex;
    double sliceRatio;              // α ∈ (0, 1]
    double fp16Tflops;              // 物理 GPU TFLOPS × α
    double memoryBandwidthGBps;     // 物理 GPU 带宽 × α
    double memoryGB;                // 物理 GPU 显存 × α
};

constexpr double FRAMEWORK_OVERHEAD = 0.95;

// LLM 时延
double ComputeLLMLatency(int inputTokens, int outputTokens,
                         const MigInstance& mig) {
    double prefill = 2.0 * 7e9 * inputTokens
                     / (mig.fp16Tflops * 1e12 * FRAMEWORK_OVERHEAD);
    double decode = static_cast<double>(outputTokens) * (14e9 + 2e9)
                    / (mig.memoryBandwidthGBps * 1e9 * FRAMEWORK_OVERHEAD);
    return prefill + decode;
}

// TTI 时延（直接使用实测数据）
double ComputeTTILatency(uint32_t physicalGpuIdx) {
    static const double measured[] = {8.5, 6.8, 4.2};
    return measured[physicalGpuIdx];
}

// ITI 时延 = TTI + 0.1s VAE 编码
double ComputeITILatency(uint32_t physicalGpuIdx) {
    return ComputeTTILatency(physicalGpuIdx) + 0.1;
}
```

---

## 7. 关键发现

1. **LLM decode 是性能瓶颈**：7B LLM 在 A100 上，Prefill 仅 26ms，但 Decode 需要 1.9s（232 tokens）。Decode 占总时延的 98%+，因为每个 token 生成都要加载 16GB 的模型权重和 KV cache。
2. **LLM decode 受限于显存带宽**：A100 整卡（2039 GB/s）时 decode 为 1.9s，但 2/7 MIG 切分（583 GB/s）时 decode 达 6.7s，时延增加 3.5 倍。
3. **A100 比 V100 快 2.3x**：LLM 总时延 1.9s vs 4.4s，与带宽比（2039/900 = 2.3x）接近，因为 decode 是带宽瓶颈。
4. **A10 和 V100 算力相同（125 TFLOPS），但 V100 更快**：V100 带宽 900 GB/s > A10 带宽 600 GB/s，LLM 时延 4.4s vs 6.6s。

---

## 8. 数据来源

### GPU 硬件规格

| GPU | 来源 |
|---|---|
| V100 | https://www.nvidia.com/en-us/data-center/tesla-v100/ |
| A10 | https://www.nvidia.com/en-us/data-center/products/a10-gpu/ |
| A100 80GB | https://www.nvidia.com/en-us/data-center/a100/ |

### LLM 模型参数

| 参数 | 值 | 来源 |
|---|---|---|
| 模型参数量 | 7B | LLaMA-2 论文：https://arxiv.org/abs/2307.09288 |
| 模型权重大小 | 14 GB (FP16) | 7B × 2 bytes/param |
| KV cache | 2 GB | vLLM 论文：https://arxiv.org/abs/2309.06180 |

### LLM Token 分布

| 参数 | 来源 |
|---|---|
| 输入/输出长度分布 | BurstGPT 数据集（Wang et al., 2024, arXiv:2401.17644） |
| Token 计算规则 | OpenAI：https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them |

### TTI/ITI 模型参数

| 参数 | 值 | 来源 |
|---|---|---|
| SDXL 总参数量 | 5.2B | SDXL 论文：https://arxiv.org/abs/2307.01952 |
| 模型权重大小 | 10.4 GB (FP16) | 5.2B × 2 bytes/param |
| CLIP 最大 token 数 | 77 | https://github.com/openai/CLIP |
| VAE 编解码时延 | 0.1 s | LDM 论文：https://arxiv.org/abs/2112.10752 |

### TTI/ITI 实测时延

| GPU | 时延 | 来源 |
|---|---|---|
| V100 | 8.5 s | 实测数据（2026-07） |
| A10 | 6.8 s | 实测数据（2026-07） |
| A100 80GB | 4.2 s | 实测数据（2026-07） |

测试条件：SDXL 1024×1024，20-25 步去噪。

