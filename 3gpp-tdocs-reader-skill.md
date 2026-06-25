# 3GPP TDocs Reader & Summarizer

> 自动下载 3GPP SA2 会议提案、按 Key Issue 筛选、逐篇阅读并生成结构化总结的完整工作流。

## 工作流程总览

```
0. 解析会议号 → 1. 下载 TDoc Excel → 2. 解析 Excel 筛选 KI 提案 → 3. 下载 .docx → 4. 提取文本 → 5. 阅读分析 → 6. 生成 MD 总结
```

---

## Step 0: 解析会议号 & 构造下载 URL

### 0.1 会议号格式

用户输入示例：

| 用户输入 | 解析结果 |
|----------|---------|
| `SA2#175-AH-e` | WG=SA2, Num=175, Type=AH-e |
| `175` | Num=175, WG=SA2(默认), Type=推断 |
| `SA2#173` | WG=SA2, Num=173, Type=推断 |
| `RAN1#112` | WG=RAN1, Num=112 |

### 0.2 工作组 → FTP 路径映射

| WG | FTP 子路径 |
|----|-----------|
| SA1 | `tsg_sa/WG1_Service` |
| SA2 | `tsg_sa/WG2_Arch` |
| SA3 | `tsg_sa/WG3_Security` |
| SA4 | `tsg_sa/WG4_Codec` |
| SA5 | `tsg_sa/WG5_TelecomMgmt` |
| SA6 | `tsg_sa/WG6_AppPCC` |
| RAN1 | `tsg_ran/WG1_Radio` |
| RAN2 | `tsg_ran/WG2_Radio` |
| RAN3 | `tsg_ran/WG3_Iu` |
| RAN4 | `tsg_ran/WG4_Radio` |
| CT1 | `tsg_ct/WG1_CT` |
| CT3 | `tsg_ct/WG3_CT` |
| CT4 | `tsg_ct/WG4_CT` |

> **注意**: SA2 的路径是 `WG2_Arch`（不是 `WG2_Architecture`），这是实际验证过的。

### 0.3 会议类型 → 文件夹名映射

| 类型 | 文件夹模式 | 示例 (SA2 #173) |
|------|-----------|-----------------|
| 主会议 (M) | `TSGS2_{num}_{city}_{year-month}` | `TSGS2_173_Goa_2026-02` |
| Ad-hoc 电子会 (AH-e) | `TSGS2_{num}-AH-e_Electronic_{year-month}` | `TSGS2_175-AH-e_Electronic_2026-06` |
| Ad-hoc 面对面 (AH) | `TSGS2_{num}AH_{city}_{year-month}` | `TSGS2_110AH_Sophia_2015-09` |

> **实际命名规则**: 3GPP 文件夹命名不严格统一，建议先通过 webfetch 浏览目录列表确认实际文件夹名。

### 0.4 构造下载 URL

```
基础 URL 模式:
  https://www.3gpp.org/ftp/{wg_path}/{meeting_folder}/
  https://www.3gpp.org/ftp/{wg_path}/{meeting_folder}/Docs/

示例 - SA2#173 (Goa, 2026-02):
  https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_173_Goa_2026-02/
  https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_173_Goa_2026-02/Docs/

示例 - SA2#175-AH-e (Electronic, 2026-06):
  https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_175-AH-e_Electronic_2026-06/
```

### 0.5 TDoc Index 文件

会议目录下通常有：
- `SA2-{num}_Index_{year}.zip` — 包含 TDoc 列表 Excel（最重要的文件）
- `TdocsByAgenda.htm` — 按议程排列的文档索引（HTML格式，可作备选）
- `Docs/` 子目录 — 包含所有提案的 .zip 文件

### 0.6 下载 TDoc Index Excel

```powershell
# 1. 浏览会议目录，找到 Index zip 文件
# 使用 webfetch 工具访问:
#   https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_173_Goa_2026-02/

# 2. 下载 Index zip
$url = "https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_173_Goa_2026-02/SA2-173_Index_2026.zip"
$outFile = "C:\Users\Administrator\Downloads\SA2-173_Index_2026.zip"
Invoke-WebRequest -Uri $url -OutFile $outFile -TimeoutSec 60

# 3. 解压得到 Excel
$extractPath = "C:\Users\Administrator\Downloads\SA2-173_Index"
Expand-Archive -LiteralPath $outFile -DestinationPath $extractPath -Force
# 解压后得到: SA2-173_Index_2026.xlsx
```

---

## Step 1: 解析 Excel，按 KI 筛选提案

### 1.1 安装 ImportExcel 模块（首次使用）

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser
Install-Module ImportExcel -Force -Scope CurrentUser
```

### 1.2 查看 Excel 结构

```powershell
$excelPath = "C:\Users\Administrator\Downloads\SA2-173_Index\SA2-173_Index_2026.xlsx"

# 查看所有 Sheet 名
$sheets = Get-ExcelSheetInfo -Path $excelPath
$sheets | ForEach-Object { Write-Output "$($_.Name) (Index: $($_.Index))" }
# 输出示例:
#   SA2#172_Dallas (Index: 1)
#   SA2#173_Goa (Index: 2)    ← 目标 Sheet
#   Meeting_Admin (Index: 3)
#   Schedule (Index: 4)
#   ...

# 读取目标 Sheet（使用 -NoHeader 避免重复列名报错）
$allDocs = Import-Excel -Path $excelPath -WorksheetName "SA2#173_Goa" -NoHeader

# 查看列名（前几行是表头信息，数据从约第15行开始）
$allDocs | Select-Object -First 15 | ForEach-Object {
    Write-Output "P1=$($_.P1) | P4=$($_.P4) | P5=$($_.P5) | P8=$($_.P8) | P9=$($_.P9)"
}
```

### 1.3 Excel 列结构说明

3GPP TDoc Index Excel 的关键列（使用 -NoHeader 时的列名）：

| 列名 | 含义 |
|------|------|
| P1 | 状态 (Available / S2#173 等) |
| P2 | 接收标记 / Affected To |
| P3 | 可用性标记 |
| P4 | **议程项编号** (如 `20.6.22` 对应 KI#22) |
| P5 | **文档编号** (如 `S2-2600098`) |
| P8 | **提案标题** |
| P9 | **来源公司** |
| P10 | 关联规范 |
| P11 | CR 编号 |

> **重要**: 前 ~14 行是表头/统计信息，实际提案数据从约第15行开始。

### 1.4 按议程项筛选 KI 提案

```powershell
$excelPath = "C:\Users\Administrator\Downloads\SA2-173_Index\SA2-173_Index_2026.xlsx"
$sheet = "SA2#173_Goa"
$allDocs = Import-Excel -Path $excelPath -WorksheetName $sheet -NoHeader

# KI#22 对应议程项 20.6.22
$ki22Docs = $allDocs | Where-Object {
    $_.P4 -eq '20.6.22' -and $_.P5 -match 'S2-'
}

Write-Output "KI#22 提案数: $($ki22Docs.Count)"
$ki22Docs | ForEach-Object {
    Write-Output "$($_.P5) | $($_.P9) | $($_.P8)"
}

# 提取文档编号列表，供后续下载
$docNumbers = $ki22Docs | ForEach-Object { $_.P5 }
```

### 1.5 不同 KI 的议程项映射

| KI | SA2#173 议程项 | SA2#175-AH-e 议程项 |
|----|---------------|---------------------|
| KI#19 (6G Network for AI) | 20.6.19 | 20.6.19 |
| KI#22 (6G Computing Support) | 20.6.22 | 20.6.22 |
| KI#21 (6G Data Framework) | 20.6.21 | 20.6.21 |

> 议程项编号在不同会议间通常保持一致，但建议先检查 Excel 内容确认。

---

## Step 2: 下载筛选出的 .docx 提案

### 2.1 批量下载 .zip 并解压

3GPP Docs 目录下的每个提案以 `{docNumber}.zip` 格式存储，内含 .docx 文件。

```powershell
$docsBaseUrl = "https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/TSGS2_173_Goa_2026-02/Docs"
$extractDir = "C:\Users\Administrator\Downloads\KI22_TDocs_173\Extracted"
New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

# $docNumbers 来自 Step 1.4
foreach ($doc in $docNumbers) {
    $zipUrl = "$docsBaseUrl/$doc.zip"
    $docDir = Join-Path $extractDir $doc
    New-Item -ItemType Directory -Path $docDir -Force | Out-Null
    $outFile = Join-Path $docDir "$doc.zip"
    try {
        Invoke-WebRequest -Uri $zipUrl -OutFile $outFile -TimeoutSec 30 -ErrorAction Stop
        Expand-Archive -LiteralPath $outFile -DestinationPath $docDir -Force
        Remove-Item -LiteralPath $outFile -Force -ErrorAction SilentlyContinue
        Write-Output "OK: $doc"
    } catch {
        Write-Output "FAIL: $doc - $($_.Exception.Message)"
    }
}
```

### 2.2 下载后目录结构

```
KI22_TDocs_173\Extracted\
├── S2-2600098\
│   └── S2-2600098_revXXXX_173_XXX_KI22_XXX.docx
├── S2-2600125\
│   └── S2-2600125_XXX.docx
├── S2-2600156\
│   └── S2-2600156_XXX.docx
└── ...
```

---

## Step 3: 提取 .docx 文本内容

```powershell
$baseDir = "C:\Users\Administrator\Downloads\KI22_TDocs_173\Extracted"
$textDir = "C:\Users\Administrator\AppData\Local\Temp\opencode\ki22_173_texts"
New-Item -ItemType Directory -Path $textDir -Force | Out-Null

$dirs = Get-ChildItem -LiteralPath $baseDir -Directory
foreach ($d in $dirs) {
    $docx = Get-ChildItem -LiteralPath $d.FullName -Filter "*.docx" -Recurse | Select-Object -First 1
    if ($docx) {
        $zipPath = Join-Path $textDir "$($d.Name).zip"
        $extractPath = Join-Path $textDir $d.Name
        Copy-Item -LiteralPath $docx.FullName -Destination $zipPath -Force
        Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force

        $xmlPath = Join-Path $extractPath "word\document.xml"
        if (Test-Path -LiteralPath $xmlPath) {
            [xml]$xml = Get-Content -LiteralPath $xmlPath -Encoding UTF8
            $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
            $ns.AddNamespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")
            $paragraphs = $xml.SelectNodes("//w:p", $ns)
            $text = ""
            foreach ($p in $paragraphs) {
                $runs = $p.SelectNodes(".//w:r/w:t", $ns)
                $line = ""
                foreach ($r in $runs) { $line += $r.InnerText }
                $text += $line + "`n"
            }
            $textFile = Join-Path $textDir "$($d.Name).txt"
            Set-Content -LiteralPath $textFile -Value $text -Encoding UTF8
            $lines = (Get-Content -LiteralPath $textFile).Count
            Write-Output "$($d.Name): $lines lines"
        }
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extractPath -Recurse -Force -ErrorAction SilentlyContinue
    }
}
```

---

## Step 4: 阅读分析每篇提案

### 4.1 批量并行阅读

将提案分为 3 批（每批约 15 篇），使用 Task 工具并行阅读：

```
Batch 1: S2-2600098 ~ S2-2600374 (前15篇)
Batch 2: S2-2600383 ~ S2-2600486 (中15篇)
Batch 3: S2-2600487 ~ S2-2601642 (后15篇)
```

### 4.2 每篇提案提取信息

对每篇提案提取以下信息：

| 字段 | 说明 |
|------|------|
| 文档编号 | S2-XXXXXXX |
| 来源公司 | 如 Huawei, Samsung 等 |
| 标题 | 提案标题 |
| 对应 Bullet | KI#22 的 bullet #1/#2/#3/#4 |
| 核心方案 | 2-4 句话概括 |
| 新 NF/架构 | 提出的新网络功能或架构元素 |
| 关键流程 | 定义的信令流程/调用流程 |

---

## Step 5: 生成结构化 Markdown 总结

### 5.1 输出文档结构

```markdown
# SA2#{会议号} KI#{KI号} ({KI标题}) 提案总结

## 一、总览
- 会议信息、提案总数、来源公司列表

## 二、按 Solution 分类总览
### Solution #X.1: [标题]
**对应 KI#X Bullet Y & Z**

| 提案编号 | 来源公司 | 标题/主题 |
|---------|---------|----------|

**Variants/Options 映射表:**

| Option | 描述 | 支持提案 |
|--------|------|---------|

**Solution 总结:**
[技术方向分析]

## 三、各公司技术方向对比表

| 公司 | 核心 NF/方案 | 关键特色 |
|------|------------|---------|

## 四、各提案详细总结
### S2-XXXXXXX (公司) - 标题
[1段详细技术总结]
```

### 5.2 Solution 总结应覆盖

1. **架构选择**: 引入哪些新 NF？复用现有 NF？
2. **信令路径**: NAS vs UP vs AF 代理
3. **关键流程**: 注册、发现、通信、终止
4. **各公司差异**: 每家公司方案的独特之处
5. **共识方向**: 多数提案一致的地方
6. **分歧方向**: 提案间存在争议的地方

### 5.3 写入文件

```powershell
$outputPath = "C:\Users\Administrator\Desktop\OpenCodeDiscussion\173_KI22.md"
Set-Content -LiteralPath $outputPath -Value $markdownContent -Encoding UTF8
```

---

## 常见问题

### 3GPP FTP 无法访问？
1. 尝试 VPN 或公司内网
2. 尝试 3GPP Portal: `https://portal.3gpp.org/`（需登录）
3. 请用户手动下载 Excel 并提供本地路径
4. 使用 webfetch 工具浏览 `https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/` 目录

### Excel 列名不匹配？
1. 使用 `$allDocs[0].PSObject.Properties.Name` 检查实际列名
2. 3GPP Index Excel 有重复列名，必须使用 `-NoHeader` 参数
3. 数据列名为 P1, P2, P3... P40

### .docx 下载失败？
1. 确认文档编号正确（如 `S2-2600098`）
2. 3GPP 上存储的是 .zip 格式（不是 .docx），需要先下载 .zip 再解压
3. 文件名可能含修订后缀（如 `_rev3`）

---

## 实际使用案例

### 案例 1: SA2#175-AH-e KI#19

```
用户: "请帮我下载 SA2#175-AH-e 的 KI#19 提案并总结"

执行流程:
1. 解析: WG=SA2, Num=175, Type=AH-e
2. 浏览: https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/ → 找到 TSGS2_175-AH-e_Electronic_2026-06
3. 下载 Index zip → 解压得到 Excel
4. 解析 Excel → 筛选议程项 20.6.19 → 40 篇提案
5. 批量下载 40 个 .zip → 解压得到 .docx
6. 提取文本 → 逐篇阅读 → 生成 175_KI19.md
```

### 案例 2: SA2#173 KI#22

```
用户: "请帮我下载 SA2#173 次会议 KI22 的提案并总结"

执行流程:
1. 解析: WG=SA2, Num=173, Type=推断为M(主会议)
2. 浏览: https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/ → 找到 TSGS2_173_Goa_2026-02
3. 下载 SA2-173_Index_2026.zip → 解压
4. 读取 Sheet "SA2#173_Goa" → 筛选议程项 20.6.22 → 45 篇提案
5. 批量下载 45 个 .zip → 解压
6. 提取文本 → 3 批并行阅读 → 生成 173_KI22.md
```

### 案例 3: 从本地文件夹直接阅读

```
用户: "请阅读 C:\Users\Administrator\Downloads\KI19_TDocs\Extracted 下的所有提案并总结"

执行流程:
1. 列出所有子目录
2. 提取每篇 .docx 文本
3. 逐篇阅读 → 按 Solution Variant 分类 → 生成 MD
```

---

## 关键经验总结

| 要点 | 说明 |
|------|------|
| SA2 FTP 路径 | `WG2_Arch`（不是 `WG2_Architecture`） |
| Excel 读取 | 必须用 `-NoHeader`，列名为 P1~P40 |
| 提案存储格式 | 3GPP 上是 .zip（内含 .docx），不是直接 .docx |
| 文件夹命名 | 不严格统一，需先浏览确认实际名称 |
| Sheet 名 | 包含会议号和城市名，如 `SA2#173_Goa` |
| 议程项与 KI 映射 | 如 `20.6.22` = KI#22, `20.6.19` = KI#19 |
| 并行阅读 | 分 3 批用 Task 工具并行处理，大幅提升效率 |
