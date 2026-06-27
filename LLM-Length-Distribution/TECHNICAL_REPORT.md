# LLM 输入/输出长度分布建模技术报告

> **版本**: v1.0  
> **日期**: 2026-06-27  
> **数据集**: BurstGPT (Azure OpenAI GPT, Conversation log)

---

## 1. 研究目标

在 LLM 推理系统的设计、仿真和容量规划中，需要准确刻画输入长度（input token length）和输出长度（output token length）的分布。本报告的目标是：

1. 确定 LLM 输入/输出长度的分布特征
2. 找到可用于仿真的抽样方法

---

## 2. 数据来源

### 2.1 BurstGPT 数据集

采用 **BurstGPT** (Wang et al., 2024, arXiv:2401.17644)，这是目前最大的公开 LLM 推理 workload trace 数据集：

| 属性 | 值 |
|------|-----|
| 来源 | Azure OpenAI GPT 服务（Microsoft Azure） |
| 规模 | 1031 万条 trace，213 天 |
| 模型 | ChatGPT (GPT-3.5) + GPT-4 |
| 字段 | Timestamp, Session ID, Elapsed time, Model, Request tokens, Response tokens, Total tokens, Log Type |

### 2.2 数据清洗

**第一步：区分 Log Type**

BurstGPT 包含两类请求：
- **API log**（89%）：程序化 API 调用，输入中位数 234 tokens，输出中位数 27 tokens
- **Conversation log**（11%）：ChatGPT 网页对话，输入中位数 494 tokens，输出中位数 232 tokens

两者是完全不同的 workload，混合在一起会导致分布严重扭曲。

**第二步：选择 Conversation log**

本研究聚焦于 **Conversation log**，理由：
- 代表人类直接与 LLM 对话的典型场景
- 输入包含完整对话历史（system prompt + 所有历史轮次），更能反映真实推理负载
- API log 中存在大量异常短响应（response=7 占 15.5%，response=2 占 8.7%），疑似错误/拒绝模板

**第三步：过滤无效样本**

- 去除 Request tokens = 0 或 Response tokens = 0（失败请求）
- 最终有效样本：**145,717 条**（输入），**145,707 条**（输出）

### 2.3 数据特征

#### 输出长度（Response tokens）

| 统计量 | 值 |
|--------|-----|
| 均值 | 265.0 tokens |
| 中位数 | 232 tokens |
| 标准差 | 221.6 |
| 偏度 | 1.44（右偏） |
| 峰度 | 4.57（重尾） |
| 变异系数 | 0.84 |
| 范围 | [1, 2048] |

#### 输入长度（Request tokens）

| 统计量 | 值 |
|--------|-----|
| 均值 | 760.8 tokens |
| 中位数 | 547 tokens |
| 标准差 | 772.7 |
| 偏度 | 2.28（右偏） |
| 峰度 | 8.55（重尾） |
| 变异系数 | 1.02 |
| 范围 | [1, 29665] |

#### 输入 vs 输出对比

| 指标 | 输出长度 | 输入长度 |
|------|---------|---------|
| 均值 | 265.0 | 760.8 |
| 中位数 | 232 | 547 |
| 标准差 | 221.6 | 772.7 |

**输入远长于输出**，原因：Conversation log 的 `Request tokens` 包含整个对话历史（system prompt + 所有历史轮次的问答），而 `Response tokens` 仅是当前这一轮的回答。

---

## 4. 经验分布抽样方法

### 4.1 方法选择

鉴于参数化分布拟合效果不佳（所有候选分布的 KS p-value 均为 0.00），采用 **经验分布抽样（Empirical Distribution Sampling）**：

1. 将长度按 bin size 分桶
2. 统计每个 bin 的频率作为概率
3. 抽样时：先按概率抽 bin，再在 bin 内均匀抽样

### 4.2 参数选择

| | 输出长度 | 输入长度 |
|---|---------|---------|
| Bin size | 10 | 3 |
| 非空 bin 数 | 205 | 1,748 |
| 总 bin 数 | 205 | 9,889 |

输入长度分布更分散，因此使用更小的 bin size（3 vs 10）。

### 4.3 实现

```python
import numpy as np

def sample_length(n_samples, bins, probs, bin_size):
    """
    从经验分布中抽样
    
    Args:
        n_samples: 抽样数量
        bins: bin 边界数组 (shape: n_bins+1)
        probs: 每个 bin 的概率 (shape: n_bins)
        bin_size: bin 宽度
    
    Returns:
        抽样得到的长度数组 (shape: n_samples)
    """
    sampled_bins = np.random.choice(len(bins)-1, size=n_samples, p=probs)
    sampled_values = bins[sampled_bins] + np.random.uniform(0, bin_size, n_samples)
    return sampled_values.astype(int)
```

### 4.4 验证结果

#### 输出长度（bin=10）

| 指标 | 原始数据 | 抽样数据 |
|------|---------|---------|
| Mean | 265.0 | 264.2 |
| Median | 232 | 233 |
| Std | 221.6 | 220.5 |

**KS 检验**：stat = 0.0026, p-value = 0.815

#### 输入长度（bin=3）

| 指标 | 原始数据 | 抽样数据 |
|------|---------|---------|
| Mean | 760.8 | 758.2 |
| Median | 547 | 549 |
| Std | 772.7 | 764.4 |

**KS 检验**：stat = 0.0021, p-value = 0.962

两个 KS p-value 均远大于 0.05，**无法拒绝**"来自同一分布"的假设。

### 4.5 CCDF 对比

原始数据和抽样数据的 CCDF 曲线几乎完全重合，说明经验分布抽样完美复现了原始分布的尾部行为。

---

## 5. 存储与使用

### 5.1 存储开销

| | 输出长度 | 输入长度 |
|---|---------|---------|
| Bin 数量 | 205 | 9,889 |
| 存储大小 | ~1.6 KB | ~79 KB |
| 文件格式 | CSV (bin_start, probability) | CSV (bin_start, probability) |

```python
# 保存
np.savetxt('output_bin_probs.csv', np.column_stack([bins_out, probs_out]),
           delimiter=',', header='bin_start,probability')
np.savetxt('input_bin_probs.csv', np.column_stack([bins_in, probs_in]),
           delimiter=',', header='bin_start,probability')

# 加载
data_out = np.loadtxt('output_bin_probs.csv', delimiter=',', skiprows=1)
bins_out = np.arange(0, 2050, 10)
probs_out = data_out[:, 1]

data_in = np.loadtxt('input_bin_probs.csv', delimiter=',', skiprows=1)
bins_in = np.arange(0, 29667, 3)
probs_in = data_in[:, 1]
```

### 5.2 使用示例

```python
# 抽样 1000 个 (输入长度, 输出长度) 对
input_lengths = sample_length(1000, bins_in, probs_in, bin_size=3)
output_lengths = sample_length(1000, bins_out, probs_out, bin_size=10)

# 计算总 token 消耗
total_tokens = input_lengths + output_lengths
print(f"平均总 tokens: {total_tokens.mean():.0f}")
print(f"P95 总 tokens: {np.percentile(total_tokens, 95):.0f}")
```

### 5.3 适用范围

- **适用**：仿真 LLM 推理系统的输入/输出长度分布
- **适用**：容量规划、成本估算、延迟建模
- **适用**：排队论分析（M/G/1 模型中的服务时间分布）
- **不适用**：需要精确建模尾部极端值（>99.9% 分位数）的场景
- **注意**：此分布基于 Conversation log，API log 的分布完全不同

---

## 6. 局限性

1. **数据集限制**：仅基于 BurstGPT 的 Conversation log（~14.6 万条），来自 Azure OpenAI GPT 服务
2. **时间范围**：数据收集于 2023 年，模型行为可能已变化
3. **模型覆盖**：仅包含 GPT-3.5 和 GPT-4，未覆盖其他模型（Llama、Claude 等）
4. **语言**：数据以英文为主，其他语言的分布可能不同
5. **动态性**：LLM 的输入/输出长度分布可能随模型更新、用户行为变化而漂移
6. **输入长度定义**：`Request tokens` 包含完整对话历史，不是单个 prompt 的长度

---

## 7. 结论

1. **LLM 输入/输出长度不服从简单的参数化分布**（log-normal、gamma、weibull 等均被 KS 检验拒绝）
2. **经验分布抽样是最佳方案**：
   - 输出长度（bin=10）：KS=0.0026，p=0.815
   - 输入长度（bin=3）：KS=0.0021，p=0.962
3. **存储开销极小**：输出长度 ~1.6 KB，输入长度 ~79 KB
4. **实现简单**：两行代码即可完成抽样
5. **输入远长于输出**：输入中位数 547 tokens vs 输出中位数 232 tokens，因为 Conversation log 的输入包含完整对话历史

---

## 参考文献

1. Wang, Y., et al. (2024). "BurstGPT: A Real-world Workload Dataset to Optimize LLM Serving Systems." arXiv:2401.17644
2. Perez-Ramirez, D.F., Kostic, D., & Boman, M. (2025). "CASTILLO: Characterizing Response Length Distributions of Large Language Models." arXiv:2505.16881
3. Yang, Y., Xu, Y., & Jiao, L. (2024). "A Queueing Theoretic Perspective on Low-Latency LLM Inference with Variable Token Length." arXiv:2407.05347

---

## 附录

### A. 输出长度分布数据（前 20 个 bin）

| Bin 范围 | 概率 (%) | 累积概率 (%) |
|---------|---------|-------------|
| [0-10) | 3.90 | 3.90 |
| [10-20) | 4.63 | 8.53 |
| [20-30) | 4.08 | 12.61 |
| [30-40) | 3.11 | 15.72 |
| [40-50) | 2.52 | 18.24 |
| [50-60) | 2.33 | 20.57 |
| [60-70) | 2.17 | 22.74 |
| [70-80) | 2.02 | 24.76 |
| [80-90) | 2.00 | 26.76 |
| [90-100) | 1.86 | 28.62 |
| [100-110) | 1.67 | 30.29 |
| [110-120) | 1.73 | 32.02 |
| [120-130) | 1.66 | 33.68 |
| [130-140) | 1.61 | 35.29 |
| [140-150) | 1.53 | 36.82 |
| [150-160) | 1.56 | 38.38 |
| [160-170) | 1.59 | 39.97 |
| [170-180) | 1.58 | 41.55 |
| [180-190) | 1.56 | 43.11 |
| [190-200) | 1.58 | 44.69 |

完整数据见 `results/output_bin_probs.csv`。

### B. 输入长度分布数据（前 20 个非空 bin）

| Bin 范围 | 概率 (%) | 累积概率 (%) |
|---------|---------|-------------|
| [6-9) | 0.07 | 0.07 |
| [9-12) | 0.30 | 0.37 |
| [12-15) | 0.89 | 1.26 |
| [15-18) | 1.56 | 2.82 |
| [18-21) | 1.71 | 4.53 |
| [21-24) | 1.55 | 6.08 |
| [24-27) | 1.45 | 7.53 |
| [27-30) | 1.21 | 8.74 |
| [30-33) | 1.03 | 9.77 |
| [33-36) | 0.89 | 10.66 |
| [36-39) | 0.84 | 11.50 |
| [39-42) | 0.75 | 12.25 |
| [42-45) | 0.62 | 12.87 |
| [45-48) | 0.63 | 13.50 |
| [48-51) | 0.57 | 14.07 |
| [51-54) | 0.52 | 14.59 |
| [54-57) | 0.48 | 15.07 |
| [57-60) | 0.45 | 15.52 |
| [60-63) | 0.45 | 15.97 |
| [63-66) | 0.40 | 16.37 |

完整数据见 `results/input_bin_probs.csv`。

### C. 代码仓库

所有代码位于 `C:\Users\Administrator\Desktop\LLM-Length-Distribution\`：

- `main.py` — 参数化分布拟合主程序
- `bin_sampling.py` — 输出长度经验分布抽样
- `input_bin_sampling.py` — 输入长度经验分布抽样
- `src/` — 数据加载、拟合、评估、可视化模块
- `plots/` — 所有图表
- `results/` — 拟合结果和概率数据 CSV
