# LLM 输入/输出长度经验分布抽样

基于 BurstGPT 数据集，对 LLM 输入/输出 token 长度进行经验分布建模与抽样。

## 数据集

**BurstGPT**：来自 Azure OpenAI GPT 服务的 1031 万条真实推理 trace，覆盖 213 天。
- 论文：https://arxiv.org/abs/2401.17644
- 代码：https://github.com/HPMLL/BurstGPT

本项目使用其中的 **Conversation log** 子集（约 14.5 万条有效样本）。

## 方法

参数化分布拟合（log-normal、gamma、weibull 等）均被 KS 检验拒绝，因此采用**经验分布抽样**：

1. 按固定宽度分桶（输出：bin=10，输入：bin=3）
2. 统计每个桶的频率作为概率
3. 抽样：先按概率抽桶，再在桶内均匀抽样

### 结果

| | 输出长度 | 输入长度 |
|---|---|---|
| 桶宽度 | 10 | 3 |
| 非空桶数 | 197 | 1,748 |
| KS 统计量 | 0.0026 | 0.0024 |
| KS p 值 | 0.815 | 0.886 |

两个 p 值均远大于 0.05，抽样数据与原始分布在统计上无法区分。

## 使用方法

```bash
# 安装依赖
pip install -r requirements.txt

# 下载 BurstGPT 数据（将 CSV 放入 data/ 目录）
# https://github.com/HPMLL/BurstGPT

# 运行
python main.py
```

## 输出文件

- `results/output_bin_probs.csv` — 输出长度各桶概率
- `results/input_bin_probs.csv` — 输入长度各桶概率
- `results/output_validation.json` — 输出长度 KS 检验结果
- `results/input_validation.json` — 输入长度 KS 检验结果
- `plots/output_sampling.png` — 输出长度抽样可视化
- `plots/input_sampling.png` — 输入长度抽样可视化

## 在其他项目中使用

```python
import numpy as np

# 加载已保存的分布
output_data = np.loadtxt("results/output_bin_probs.csv", delimiter=",", skiprows=1)
input_data = np.loadtxt("results/input_bin_probs.csv", delimiter=",", skiprows=1)

output_bins = np.arange(0, 2050, 10)
output_probs = output_data[:, 1]

input_bins = np.arange(0, 29667, 3)
input_probs = input_data[:, 1]

# 抽样函数
def sample(n, bins, probs, bin_size):
    idx = np.random.choice(len(bins) - 1, size=n, p=probs)
    return (bins[idx] + np.random.uniform(0, bin_size, n)).astype(int)

# 抽样 1000 个 (输入长度, 输出长度) 对
output_lengths = sample(1000, output_bins, output_probs, 10)
input_lengths = sample(1000, input_bins, input_probs, 3)
```

## 项目结构

```
├── main.py              # 流水线入口
├── src/
│   ├── data_loader.py   # BurstGPT 数据加载与过滤
│   ├── sampling.py      # 经验分布构建、抽样、KS 验证
│   └── visualize.py     # 可视化（直方图、CCDF 对比）
├── data/                # BurstGPT CSV 文件（不入库）
├── results/             # 桶概率 CSV 和验证 JSON
├── plots/               # 可视化图表
├── requirements.txt
├── TECHNICAL_REPORT.md  # 完整技术报告
└── README.md
```

## 参考文献

1. Wang, Y., et al. (2024). "BurstGPT: A Real-world Workload Dataset to Optimize LLM Serving Systems." arXiv:2401.17644
2. Perez-Ramirez, D.F., et al. (2025). "CASTILLO: Characterizing Response Length Distributions of Large Language Models." arXiv:2505.16881
3. Yang, Y., et al. (2024). "A Queueing Theoretic Perspective on Low-Latency LLM Inference with Variable Token Length." arXiv:2407.05347
