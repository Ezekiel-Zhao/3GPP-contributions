---
name: 3gpp-review
description: Use when the user asks to read, summarize, or analyze 3GPP contribution documents (TDocs) for a Key Issue (KI). Handles downloading the TDoc list Excel from 3GPP by meeting number (e.g., SA2#175-AH-e), downloading individual .docx proposals, extracting text, reading each proposal, and generating a structured markdown summary organized by Solution Variant. Triggers on phrases like "read TDocs", "summarize KI proposals", "3GPP contribution summary", "download and analyze SA2 documents", "download meeting documents", "总结提案", "分析KI".
---

# 3GPP TDocs Review & Summarizer

自动化下载、解析、分析 3GPP 工作组贡献文档（TDocs），针对指定 Key Issue (KI) 生成结构化中文总结。

**IMPORTANT**: Follow each step EXACTLY as written. Do NOT skip steps. Do NOT guess URLs or folder names. Execute every PowerShell command as-is.

---

## WORKFLOW OVERVIEW (7 steps, execute in order)

```
Step 0: Initialize cache & environment
Step 1: Find the meeting folder on 3GPP website
Step 2: Download the TDoc Index Excel
Step 3: Parse Excel, filter KI proposals, download .zip files
Step 4: Extract text from .docx files (with table & heading support)
Step 5: Read proposals in parallel batches (use task tool)
Step 6: Verify coverage & generate structured Markdown summary
```

---

## STEP 0: Initialize Cache & Environment

### 0.1 Set up cache directory structure

All downloads and intermediate files use a persistent cache so re-runs skip already-downloaded files.

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$cacheRoot = "C:\Users\Administrator\Downloads\3gpp_cache"
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null

# Sub-directories will be created dynamically:
#   $cacheRoot\{meetingFolder}\index\       - Index Excel
#   $cacheRoot\{meetingFolder}\docs\        - Downloaded .zip/.docx
#   $cacheRoot\{meetingFolder}\texts\       - Extracted .txt files
#   C:\Users\Administrator\Desktop\OpenCodeDiscussion\  - Final output
# === END OF BLOCK ===
```

### 0.2 Ensure ImportExcel module is available

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
if (-not (Get-Module -ListAvailable -Name ImportExcel)) {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser
    Install-Module ImportExcel -Force -Scope CurrentUser
    Write-Output "ImportExcel installed."
} else {
    Write-Output "ImportExcel already available."
}
# === END OF BLOCK ===
```

---

## STEP 1: Find the Meeting Folder

### What you need from the user

The user provides a meeting identifier and optionally a KI number. Parse them:

| User says | WG | Number | Type | KI |
|-----------|-----|--------|------|----|
| `SA2#175-AH-e KI#22` | SA2 | 175 | AH-e | 22 |
| `SA2#173 KI#19` | SA2 | 173 | (unknown) | 19 |
| `174` | SA2 (default) | 174 | (unknown) | (ask user) |

### Supported Working Groups

| WG | FTP Path |
|----|----------|
| SA2 | `tsg_sa/WG2_Arch` |
| SA1 | `tsg_sa/WG1_Serv` |
| SA3 | `tsg_sa/WG3_Security` |
| SA5 | `tsg_sa/WG5_OAM` |
| CT1 | `tsg_ct/WG1_NAS` |
| CT4 | `tsg_ct/WG4_MAP` |

**CRITICAL**: SA2 FTP path is `WG2_Arch` NOT `WG2_Architecture`.

### How to find the exact folder name

**You MUST use the `webfetch` tool to browse the directory listing.** Folder names include city and date and are NOT predictable.

```
Use webfetch tool with:
  url: "https://www.3gpp.org/ftp/{wgPath}/"
  format: "text"
```

Then search the response text for the meeting number.

**Known folder name examples** (for reference only, always verify):

```
SA2#173 → TSGS2_173_Goa_2026-02
SA2#174 → TSGS2_174_Malta_2026-04
SA2#175 → TSGS2_175_Dalian_2026-05
SA2#175-AH-e → TSGS2_175-AH-e_Electronic_2026-06
```

### What to record

After finding the folder, write down these values for use in later steps:

```
$wgPath = "tsg_sa/WG2_Arch"
$meetingFolder = "TSGS2_173_Goa_2026-02"   ← replace with actual
$meetingNum = "173"                          ← extract number
$meetingLocation = "Goa"                     ← extract city
$meetingDate = "2026-02"                     ← extract date
$wgPrefix = "S2"                             ← document number prefix (S1/S2/S3/...)
```

### If webfetch fails or listing is truncated

If the directory listing is very long and appears truncated, use `grep` on the output to search for the meeting number. If webfetch fails entirely:

> "3GPP FTP 目录无法访问。请手动访问 https://www.3gpp.org/ftp/{wgPath}/ 找到对应会议的文件夹名，然后告诉我。"

---

## STEP 2: Download the TDoc Index Excel

### 2.1 Browse the meeting folder to find the Index zip

```
Use webfetch tool with:
  url: "https://www.3gpp.org/ftp/{wgPath}/{meetingFolder}/"
  format: "text"
```

Look for a file matching pattern: `SA2-{number}_Index_{year}.zip`

### 2.2 Download and extract (with cache check)

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$indexUrl = "https://www.3gpp.org/ftp/{wgPath}/{meetingFolder}/{indexZipName}"  # ← replace
$indexDir = Join-Path $cacheRoot "$meetingFolder\index"
$zipOut = Join-Path $indexDir $indexZipName

# Skip download if already cached
if (Test-Path -LiteralPath $zipOut) {
    $fileSize = (Get-Item -LiteralPath $zipOut).Length
    if ($fileSize -gt 1000) {
        Write-Output "Index zip already cached ($fileSize bytes). Skipping download."
    } else {
        Remove-Item -LiteralPath $zipOut -Force
    }
}

if (-not (Test-Path -LiteralPath $zipOut)) {
    New-Item -ItemType Directory -Path $indexDir -Force | Out-Null
    Invoke-WebRequest -Uri $indexUrl -OutFile $zipOut -TimeoutSec 120
    $fileSize = (Get-Item -LiteralPath $zipOut).Length
    if ($fileSize -lt 1000) {
        Write-Output "ERROR: Downloaded file is too small ($fileSize bytes). Likely a 404 page."
        Remove-Item -LiteralPath $zipOut -Force
    } else {
        Write-Output "Downloaded: $fileSize bytes"
    }
}

$extractPath = Join-Path $indexDir "extracted"
if (Test-Path -LiteralPath $zipOut) {
    Expand-Archive -LiteralPath $zipOut -DestinationPath $extractPath -Force
    Get-ChildItem -LiteralPath $extractPath -Recurse | Select-Object FullName, Length
}
# === END OF BLOCK ===
```

### 2.3 Verify the Excel file

After extraction, find the `.xlsx` file. Record its full path as `$excelPath`.

---

## STEP 3: Parse Excel, Filter KI Proposals, Download .zip Files

### 3.1 List Excel sheets and find the target

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$sheets = Get-ExcelSheetInfo -Path $excelPath
Write-Output "=== Sheet Names ==="
$sheets | ForEach-Object { Write-Output "  $($_.Name) (Index: $($_.Index))" }
# === END OF BLOCK ===
```

Find the sheet matching the meeting (e.g., `SA2#173_Goa`). Record as `$sheetName`.

### 3.2 Read the sheet with dynamic column detection

**CRITICAL**: You MUST use `-NoHeader` parameter. The 3GPP Index Excel has duplicate column headers.

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$allDocs = Import-Excel -Path $excelPath -WorksheetName $sheetName -NoHeader

Write-Output "Total rows: $($allDocs.Count)"

# Dynamically detect header row and column mapping
# Scan first 20 rows to find the one containing column labels
Write-Output "`n=== First 20 rows (for column detection) ==="
$allDocs | Select-Object -First 20 | ForEach-Object {
    $row = $_
    $vals = @()
    for ($i = 1; $i -le 15; $i++) {
        $propName = "P$i"
        $val = $row.$propName
        if ($val) { $vals += "P${i}=$val" }
    }
    Write-Output ($vals -join " | ")
}
# === END OF BLOCK ===
```

### 3.3 Identify column mapping from header row

From the output above, identify:

```
$colAgenda  = "P?"   # Column containing agenda item numbers (e.g., "20.6.22")
$colDocNum   = "P?"   # Column containing document numbers (e.g., "S2-2600098")
$colTitle    = "P?"   # Column containing proposal titles
$colSource   = "P?"   # Column containing source company names
$colStatus   = "P?"   # Column containing status (e.g., "Available")
$dataStartRow = ??     # Row number where actual data begins (after headers)
```

**Common mapping for SA2** (verify from output):

```
P1 = Status, P4 = Agenda Item, P5 = Doc Number, P8 = Title, P9 = Source
Data typically starts around row 15.
```

### 3.4 Find the agenda item for the target KI

Search the header rows for the KI description to find the agenda item number:

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$kiNumber = "22"  # ← replace with target KI number

# Search header rows for KI-related text
Write-Output "=== Searching for KI#$kiNumber in headers ==="
$allDocs | Select-Object -First 15 | ForEach-Object {
    $row = $_
    for ($i = 1; $i -le 15; $i++) {
        $propName = "P$i"
        $val = $row.$propName
        if ($val -and ($val -match "KI" -or $val -match "Key Issue" -or $val -match $kiNumber)) {
            Write-Output "Found in P${i}: $val"
        }
    }
}

# Also list all unique agenda items from data rows
Write-Output "`n=== All unique agenda items ==="
$dataRows = $allDocs | Select-Object -Skip ($dataStartRow - 1)
$dataRows | Where-Object { $_.$colDocNum -match $wgPrefix } |
    Select-Object -ExpandProperty $colAgenda -Unique |
    Sort-Object |
    ForEach-Object { Write-Output "  $_" }
# === END OF BLOCK ===
```

### 3.5 Filter proposals by agenda item

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$agendaItem = "20.6.22"  # ← replace with actual agenda item

$kiProposals = $dataRows | Where-Object {
    $_.$colAgenda -eq $agendaItem -and $_.$colDocNum -match $wgPrefix
}

Write-Output "Found $($kiProposals.Count) proposals for agenda item $agendaItem"
Write-Output "`n=== Proposal List ==="
$kiProposals | ForEach-Object {
    Write-Output "$($_.$colDocNum) | $($_.$colSource) | $($_.$colTitle)"
}

$docNumbers = @($kiProposals | ForEach-Object { $_.$colDocNum })
$docMeta = @{}
$kiProposals | ForEach-Object {
    $docMeta[$_.$colDocNum] = @{
        Source = $_.$colSource
        Title  = $_.$colTitle
    }
}
Write-Output "`nDocument numbers to download: $($docNumbers.Count)"
# === END OF BLOCK ===
```

### 3.6 Download proposal .zip files (parallel with retry)

**CRITICAL**: 3GPP stores proposals as `.zip` files, NOT `.docx`. Each `.zip` contains a `.docx` inside.

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$docsBaseUrl = "https://www.3gpp.org/ftp/{wgPath}/{meetingFolder}/Docs"  # ← replace
$docsDir = Join-Path $cacheRoot "$meetingFolder\docs"
New-Item -ItemType Directory -Path $docsDir -Force | Out-Null

# Filter out already-downloaded docs (cache check)
$toDownload = @()
foreach ($doc in $docNumbers) {
    $docDir = Join-Path $docsDir $doc
    $docxFiles = @()
    if (Test-Path -LiteralPath $docDir) {
        $docxFiles = @(Get-ChildItem -LiteralPath $docDir -Filter "*.docx" -Recurse -ErrorAction SilentlyContinue)
    }
    if ($docxFiles.Count -eq 0) {
        $toDownload += $doc
    }
}

Write-Output "Already cached: $($docNumbers.Count - $toDownload.Count)"
Write-Output "To download: $($toDownload.Count)"

# Download with parallel jobs (batches of 5)
$batchSize = 5
$downloaded = 0; $failed = 0; $retries = 2

for ($i = 0; $i -lt $toDownload.Count; $i += $batchSize) {
    $batch = $toDownload[$i..([Math]::Min($i + $batchSize - 1, $toDownload.Count - 1))]
    $jobs = @()

    foreach ($doc in $batch) {
        $zipUrl = "$docsBaseUrl/$doc.zip"
        $docDir = Join-Path $docsDir $doc
        $outFile = Join-Path $docDir "$doc.zip"

        $jobs += Start-Job -ScriptBlock {
            param($url, $dir, $file, $maxRetries)
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            for ($attempt = 1; $attempt -le $maxRetries; $attempt++) {
                try {
                    Invoke-WebRequest -Uri $url -OutFile $file -TimeoutSec 30 -ErrorAction Stop
                    $size = (Get-Item -LiteralPath $file).Length
                    if ($size -lt 500) {
                        Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
                        throw "File too small ($size bytes)"
                    }
                    Expand-Archive -LiteralPath $file -DestinationPath $dir -Force
                    Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
                    return "OK"
                } catch {
                    if ($attempt -eq $maxRetries) { return "FAIL: $($_.Exception.Message)" }
                    Start-Sleep -Seconds 2
                }
            }
        } -ArgumentList $zipUrl, $docDir, $outFile, $retries
    }

    $jobs | Wait-Job -Timeout 60 | Out-Null
    foreach ($job in $jobs) {
        $result = Receive-Job -Job $job -ErrorAction SilentlyContinue
        if ($result -eq "OK") { $downloaded++ } else { $failed++; Write-Output $result }
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
    Write-Output "Progress: $([Math]::Min($i + $batchSize, $toDownload.Count))/$($toDownload.Count)"
}

Write-Output "`nDone. Downloaded: $downloaded, Failed: $failed, Cached: $($docNumbers.Count - $toDownload.Count)"
# === END OF BLOCK ===
```

---

## STEP 4: Extract Text from .docx Files (with Table & Heading Support)

### 4.1 Full text extraction including tables and headings

This script handles:
- Paragraph text with heading level markers (`[H1]`, `[H2]`, etc.)
- Table content (converted to pipe-delimited text)
- Track changes: only extracts accepted/final text, skips deletions
- Nested table cells

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$docsDir = Join-Path $cacheRoot "$meetingFolder\docs"
$textDir = Join-Path $cacheRoot "$meetingFolder\texts"
New-Item -ItemType Directory -Path $textDir -Force | Out-Null

$dirs = Get-ChildItem -LiteralPath $docsDir -Directory
$total = $dirs.Count; $current = 0

foreach ($d in $dirs) {
    $current++
    $textFile = Join-Path $textDir "$($d.Name).txt"

    # Skip if already extracted
    if ((Test-Path -LiteralPath $textFile) -and (Get-Item -LiteralPath $textFile).Length -gt 100) {
        Write-Output "SKIP (cached): $($d.Name)"
        continue
    }

    $docx = Get-ChildItem -LiteralPath $d.FullName -Filter "*.docx" -Recurse | Select-Object -First 1
    if (-not $docx) {
        Write-Output "NO DOCX: $($d.Name)"
        continue
    }

    $workDir = Join-Path $textDir "_work_$($d.Name)"
    $zipPath = Join-Path $textDir "$($d.Name).zip"

    try {
        Copy-Item -LiteralPath $docx.FullName -Destination $zipPath -Force
        Expand-Archive -LiteralPath $zipPath -DestinationPath $workDir -Force

        $xmlPath = Join-Path $workDir "word\document.xml"
        if (-not (Test-Path -LiteralPath $xmlPath)) {
            Write-Output "NO XML: $($d.Name)"
            continue
        }

        [xml]$xml = Get-Content -LiteralPath $xmlPath -Encoding UTF8
        $ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
        $ns.AddNamespace("w", "http://schemas.openxmlformats.org/wordprocessingml/2006/main")

        $text = ""

        # Process all body children (paragraphs AND tables) in document order
        $body = $xml.SelectSingleNode("//w:body", $ns)
        if (-not $body) { $body = $xml.SelectSingleNode("//w:document/w:body", $ns) }

        foreach ($child in $body.ChildNodes) {
            if ($child.LocalName -eq "p") {
                # === PARAGRAPH ===
                $pStyle = ""
                $pPr = $child.SelectSingleNode("w:pPr/w:pStyle/@w:val", $ns)
                if ($pPr) { $pStyle = $pPr.Value }

                # Detect heading level
                $headingPrefix = ""
                if ($pStyle -match "^Heading(\d)$" -or $pStyle -match "^heading(\d)$" -or $pStyle -match "^(\d)$") {
                    $level = $Matches[1]
                    $headingPrefix = "[H$level] "
                } elseif ($pStyle -match "Title" -or $pStyle -match "title") {
                    $headingPrefix = "[H1] "
                }

                # Extract text from runs, SKIP deleted text (w:del)
                $line = ""
                $runs = $child.SelectNodes(".//w:r", $ns)
                foreach ($r in $runs) {
                    # Skip runs inside w:del (track changes deletions)
                    $parent = $r.ParentNode
                    if ($parent -and $parent.LocalName -eq "del") { continue }

                    $tNodes = $r.SelectNodes("w:t", $ns)
                    foreach ($t in $tNodes) { $line += $t.InnerText }
                }

                if ($line.Trim() -or $headingPrefix) {
                    $text += "$headingPrefix$line`n"
                }
            }
            elseif ($child.LocalName -eq "tbl") {
                # === TABLE ===
                $text += "[TABLE START]`n"
                $rows = $child.SelectNodes(".//w:tr", $ns)
                foreach ($row in $rows) {
                    $cells = $row.SelectNodes("w:tc", $ns)
                    $cellTexts = @()
                    foreach ($cell in $cells) {
                        $cellText = ""
                        $cellParas = $cell.SelectNodes(".//w:p", $ns)
                        foreach ($cp in $cellParas) {
                            $cRuns = $cp.SelectNodes(".//w:r", $ns)
                            foreach ($cr in $cRuns) {
                                $parent = $cr.ParentNode
                                if ($parent -and $parent.LocalName -eq "del") { continue }
                                $cTNodes = $cr.SelectNodes("w:t", $ns)
                                foreach ($ct in $cTNodes) { $cellText += $ct.InnerText }
                            }
                        }
                        $cellTexts += $cellText.Trim()
                    }
                    $text += ($cellTexts -join " | ") + "`n"
                }
                $text += "[TABLE END]`n"
            }
        }

        Set-Content -LiteralPath $textFile -Value $text -Encoding UTF8
        $lines = (Get-Content -LiteralPath $textFile).Count
        $tableCount = ([regex]::Matches($text, "\[TABLE START\]")).Count
        Write-Output "OK ($current/$total): $($d.Name) - $lines lines, $tableCount tables"
    }
    catch {
        Write-Output "ERROR ($current/$total): $($d.Name) - $($_.Exception.Message)"
    }
    finally {
        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
Write-Output "`nDone extracting text."
# === END OF BLOCK ===
```

---

## STEP 5: Read and Analyze Proposals

### 5.1 List extracted text files

```powershell
# === COPY AND EXECUTE THIS BLOCK ===
$textFiles = Get-ChildItem -LiteralPath $textDir -Filter "*.txt" |
    Sort-Object Name |
    ForEach-Object { $_.Name }

Write-Output "Total text files: $($textFiles.Count)"
$textFiles | ForEach-Object { Write-Output "  $_" }
# === END OF BLOCK ===
```

### 5.2 Split into batches

Split files into batches of **12-15 files** each. Use smaller batches if files are large (>500 lines each).

```
Batch 1: Files 1-15 (alphabetically)
Batch 2: Files 16-30
Batch 3: Files 31-45
Batch 4: Remaining files (if any)
```

### 5.3 Launch parallel task agents

**CRITICAL**: Send ALL batch tasks in a SINGLE message to maximize parallelism.

For each batch, use the `task` tool with `subagent_type: "general"` and this prompt structure:

```
You are analyzing 3GPP {WG} contribution documents for KI#{kiNumber}
({KI Title}) from meeting {WG}#{meetingNum} ({Location}, {Date}).

Read the following {N} text files and for EACH proposal, provide:
1. Document number (e.g., S2-XXXXXXX)
2. Source company
3. Title
4. Which Solution # it targets (e.g., #22.1, #22.2, etc.)
5. Which bullet(s) of KI#{kiNumber} it addresses
6. Core technical proposal summary (2-4 sentences in Chinese)
7. Key new network functions or architecture elements proposed
8. Key procedures or call flows defined
9. Any tables found and their content summary

The files are at: {textDir}\

Read these files:
1. {filename1}.txt (Source: {company1})
2. {filename2}.txt (Source: {company2})
...

IMPORTANT:
- Text marked with [H1], [H2] etc. are headings - use them to understand document structure
- Text between [TABLE START] and [TABLE END] are table contents - analyze them carefully
- Return your analysis in a structured format
- Be thorough: capture ALL technical details including NF names, reference points, procedure steps
- Write summaries in Chinese (中文)

Return a JSON-like structured output for each proposal.
```

### 5.4 Verify coverage after all batches complete

After all task agents return, verify:

```
Expected proposals: {docNumbers.Count}
Analyzed proposals: {count from task results}
Missing: {list any doc numbers not covered}
```

If any proposals are missing, launch an additional task agent for them.

---

## STEP 6: Verify Coverage & Generate Structured Markdown Summary

### 6.1 Output file location

```
C:\Users\Administrator\Desktop\OpenCodeDiscussion\{MeetingNumber}_KI{kiNumber}.md
```

### 6.2 REQUIRED document structure

```markdown
# {WG}#{MeetingNum} ({Location}, {Date}) KI#{kiNumber} ({KI Title}) 提案总结

## 一、总览

- **会议**: {WG}#{MeetingNum}, {Location}, {Date}
- **KI#{kiNumber}**: {KI Title}
- **议程项**: {agenda item number}
- **提案总数**: {N}篇
- **来源公司**: {list of companies}

### 与上次会议对比 (if applicable)

| 维度 | {WG}#{PrevNum} | {WG}#{MeetingNum} |
|------|---------------|------------------|
| 提案数 | X篇 | Y篇 |
| ... | ... | ... |

---

## 二、按 Solution 分类总览

### Solution #{kiNumber}.1: [Solution Title]
**对应 KI#{kiNumber} Bullet Y & Z**

| 提案编号 | 来源公司 | 标题/主题 |
|---------|---------|----------|
| S2-XXXXXXX | Company A | Brief description |

**Variants/Options:**

| Option/Variant | 描述 | 支持提案 |
|----------------|------|---------|
| Var A | Description | List of proposals |

**Solution 总结:**
[Technical summary paragraph]

---

(repeat for each Solution)

---

## 三、各公司技术方向对比表

| 公司 | 核心 NF/方案 | 关键特色 |
|------|------------|---------|
| Company A | NF name | Key differentiator |

---

## 四、各提案详细总结

### S2-XXXXXXX (Company) - Solution #XX.Y: Title
[1 paragraph detailed technical summary]

(repeat for each proposal)

---

## 五、关键分歧与共识

### 共识点
- [List of areas where most companies agree]

### 分歧点
- [List of areas where companies disagree, with supporting proposal references]

### 待进一步讨论
- [Open issues that need further discussion in next meeting]
```

### 6.3 Summary content guidelines

For each **Solution summary**, cover:
1. Architecture choices (new NFs vs reused)
2. Signaling paths (NAS vs UP vs AF-proxied)
3. Key procedures
4. What makes each company's approach unique
5. Where proposals agree (consensus)
6. Where proposals disagree (divergence)

For each **individual proposal summary**, cover:
1. Source company and title
2. Which Solution and Variant it targets
3. Core technical contribution
4. Key call flows
5. Unique aspects

---

## TROUBLESHOOTING

### Problem: "Duplicate column headers" error when reading Excel
**Solution**: You forgot `-NoHeader`. Always use:
```powershell
Import-Excel -Path $excelPath -WorksheetName $sheetName -NoHeader
```

### Problem: Cannot find proposals when filtering
**Solution**: The agenda item number may not match. Print all unique agenda items:
```powershell
$dataRows | Where-Object { $_.$colDocNum -match $wgPrefix } |
    Select-Object -ExpandProperty $colAgenda -Unique | Sort-Object
```

### Problem: .docx download returns 404
**Solution**: 3GPP stores `.zip` files, not `.docx`. Use:
```
https://www.3gpp.org/ftp/.../Docs/S2-2600098.zip   ← CORRECT
https://www.3gpp.org/ftp/.../Docs/S2-2600098.docx   ← WRONG
```

### Problem: Cannot access 3GPP FTP
**Solution**: Tell the user to manually download from:
```
https://www.3gpp.org/ftp/{wgPath}/
```
Then provide the local file path.

### Problem: Context overflow when reading proposals
**Solution**: Use smaller batches (8-10 files per task).

### Problem: Downloaded zip is too small / corrupt
**Solution**: The script checks file size < 500 bytes and re-downloads. If persistent, the document may not exist on the server.

### Problem: Text extraction produces garbled characters
**Solution**: Ensure `-Encoding UTF8` is used in both `Get-Content` and `Set-Content`.

---

## KEY FACTS CHEAT SHEET

```
3GPP base URL:         https://www.3gpp.org/ftp/
SA2 FTP path:          tsg_sa/WG2_Arch  (NOT WG2_Architecture)
SA1 FTP path:          tsg_sa/WG1_Serv
SA3 FTP path:          tsg_sa/WG3_Security
CT1 FTP path:          tsg_ct/WG1_NAS
Index file format:     SA2-{num}_Index_{year}.zip (contains .xlsx)
Excel read parameter:  -NoHeader (MANDATORY)
Column detection:      Dynamic - scan first 20 rows for headers
Common SA2 columns:    P4=Agenda, P5=DocNum, P8=Title, P9=Source
Proposal file format:  .zip (contains .docx inside)
Text extraction:       .docx → unzip → word/document.xml → parse paragraphs + tables
Track changes:         Skip w:del elements, only extract final text
Heading detection:     w:pStyle with Heading1/2/3 or Title
Table extraction:      w:tbl → w:tr → w:tc → pipe-delimited
Download strategy:     Parallel Jobs, batch of 5, with retry
Cache directory:       C:\Users\Administrator\Downloads\3gpp_cache\
Reading strategy:      Split into batches of 12-15, use task tool in parallel
Coverage check:        Verify all doc numbers analyzed before generating summary
Output language:       Chinese (中文)
Output location:       C:\Users\Administrator\Desktop\OpenCodeDiscussion\
```

---

## EXAMPLE: Complete execution for SA2#173 KI#22

```
User: "请帮我总结 SA2#173 的 KI#22 提案"

Step 0: Cache dir created, ImportExcel verified

Step 1: webfetch "https://www.3gpp.org/ftp/tsg_sa/WG2_Arch/"
        → Found: TSGS2_173_Goa_2026-02

Step 2: webfetch ".../TSGS2_173_Goa_2026-02/"
        → Found: SA2-173_Index_2026.zip
        → Downloaded to cache\TSGS2_173_Goa_2026-02\index\

Step 3: Import-Excel with -NoHeader, dynamic column detection
        → Detected: P4=Agenda, P5=DocNum, P8=Title, P9=Source
        → Filter P4 = "20.6.22" → 45 proposals
        → Parallel download (batches of 5) → 45 OK, 0 failed

Step 4: Extracted text from 45 .docx → .txt files
        → Including tables and headings, skipping track changes

Step 5: 3 parallel task batches (15+15+15)
        → All 45 proposals analyzed
        → Coverage verified: 45/45

Step 6: Generated 173_KI22.md with:
        - Overview (45 proposals, 24+ companies)
        - Solution classification (#22.1-#22.13)
        - Company comparison table
        - 45 individual proposal summaries
        - Key consensus and divergence analysis
```
