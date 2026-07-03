# SA2#175-AH-e KI#22 华为提案总结

## 一、总览

- **会议**: SA2#175-AH-e (线上会议), 2026年6月24日-7月1日
- **KI#22**: Study on Architecture for 6G System (FS_6G_ARC) - 6G Computing Support
- **议程项**: 20.6.22
- **华为提案总数**: 7篇（含1篇6家联合提案）
- **覆盖 Solution Variant**: #22.2, #22.7, #22.11, 以及新增 NOTE

---

## 二、华为提案列表

| # | 提案编号 | 标题 | Solution | 解决的问题 |
|---|---------|------|----------|-----------|
| 1 | S2-2606084 | Add new Solution Variant: No Computing Exposure from 6G CN to AF | Solution Category Overview | 在方案分类表中添加 NOTE，说明并非所有方案都需要从 6G CN 向 AF 暴露计算信息 |
| 2 | S2-2606085 | Add details for Coordination between Communication and Computing is controlled by 6G CN | #22.2 (6家联合) | 为 CN 控制的通算协调方案添加详细流程描述，包括计算资源发现、远程调用、CN 控制原因、协调机制、服务连续性等 |
| 3 | S2-2606086 | User plane protocol design coordination | #22.2 | 用户面协议栈设计，定义 Computing Layer 用于 UE 和 Computing Node 之间的任务级协调 |
| 4 | S2-2606087 | Add detailed procedure of Computing Agent for AF request | #22.2 | AF 请求场景下 Computing Agent 的详细流程，包括意图解释、资源协调、UE 组支持 |
| 5 | S2-2606088 | UDM based authorization | #22.7 | 基于 UDM 订阅数据的计算服务授权机制 |
| 6 | S2-2606089 | Monitoring event for Computing Resources status monitoring | #22.11 | 计算资源状态监控的事件订阅和上报机制 |
| 7 | S2-2606090 | Add detailed procedures of Computing Agent for UE request | #22.2 | UE 请求场景下 Computing Agent 的详细流程，包括资源规划、连接协调、迁移触发 |

---

## 三、按 Solution 分类总结

### Solution #22.2 (CN 控制的通算协调) — 5 篇

#### S2-2606085 (6家联合: Huawei, HiSilicon, Vivo, CATT, Xiaomi, ZTE)
**核心贡献**: 为 Solution #22.2 提供通用部分的详细描述

**主要内容**:
1. **计算资源发现和描述框架**
   - 参考 OpenStack 云边缘计算白皮书，定义通用计算资源描述模板
   - 计算资源类型：Software、Infrastructure、Platform、AI Model
   - 计算资源属性：Computing Node ID、功能/能力标签、容量、CPU/GPU/RAM/ROM 类型和数量、带宽等

2. **远程计算资源调用机制**
   - 客户端应用无感知远程资源（类似 JUICE 的 API 注入）
   - OS 识别库类型（计算资源类型）并发送给 modem
   - CMF 基于性能要求选择 Computing Node

3. **CN 控制计算的3个原因**
   - 新收入和network资源高效利用（AI4Network）
   - 支持必须在网络执行的计算任务（如环境重构，原始数据不能出网）
   - 联合控制通信和计算服务（保证 E2E 延迟）

4. **通信和计算协调机制**
   - 会话级协调（控制面）：CP NF（CMF/Computing Agent/PCF）确定通信和计算参数
   - 任务级协调（用户面）：基于 on-path 信息进行计算调度和负载均衡
   - Computing Enforcement Rule：包含 Computing Session ID、Rule ID、Precedence、Packet filters、Computing latency、Computing resource type

5. **计算服务连续性（CSC）**
   - 定义 Computing Service Continuity Policy (CSCP)
   - 引入 Combined Communication and Computing Identifier (CCCID) 关联计算会话和 PDU 会话
   - CMF 维护通信和计算上下文

6. **详细流程**
   - 计算服务请求流程（6步）
   - 计算服务释放流程（3步）
   - 计算资源注册流程（3步）
   - 服务连续性流程（6步）
   - 用户面动态协调流程（2步）
   - 分布式计算流程（3步）

#### S2-2606086 (Huawei, HiSilicon)
**核心贡献**: 用户面协议栈设计

**主要内容**:
1. **协议栈结构**（UE ↔ 6G RAN ↔ 6G Anchor UPF ↔ Computing Node）
   - **PDU Session Layer**: 基于 PDU Session 和 GTP-U 隧道
   - **Computing Layer**: 携带 Task Identification information 和 Task priority & monitoring information
   - **API Layer**: 计算层负载（未指定）

2. **Computing Layer 功能**
   - UE 和 Computing Node 之间的任务级协调
   - 携带任务标识信息用于 Computing Node 负载均衡
   - UPF 也可向 Computing Node 发送节点级任务信息

#### S2-2606087 (Huawei, HiSilicon)
**核心贡献**: AF 请求场景下 Computing Agent 详细流程

**主要内容**:
1. **AF 计算服务请求参数**
   - AF Computing Service Session ID、UE ID/UE组信息、Application ID
   - 计算资源类型、整体延迟要求、整体带宽要求
   - 请求服务时间、请求服务区域

2. **Computing Agent 功能**
   - 解释 AF 请求（意图）并识别计算服务
   - 执行授权
   - 编排计算流程（via CMF）和连接流程（via Connection Agent）
   - 支持大规模 UE 和地理区域（可分配多个 CMF）

3. **资源协调选择流程**（10步）
   - AF → Computing Agent → CMF（选择 Computing Node）
   - Computing Agent → Connection Agent（协调 UPF 选择）
   - Connection Agent ↔ 6G SMF（检查 UPF 支持）
   - Computing Agent 为每个 UE 选择 Computing Node
   - 返回 AF 计算服务响应

4. **UE 组支持**
   - 支持 XR 服务等多用户场景
   - 参考 Unity/Unreal 的 multi-presence SDK

#### S2-2606090 (Huawei, HiSilicon)
**核心贡献**: UE 请求场景下 Computing Agent 详细流程

**主要内容**:
1. **UE 计算服务请求参数**
   - 计算资源类型、整体 RTT 延迟、整体带宽要求
   - xPU 规格和数量要求（可选）
   - UE ID、请求服务区域、请求服务时间、意图（可选）

2. **Computing Agent 功能**
   - 解释计算请求（意图）并生成计算和连接要求
   - 执行授权
   - 编排 CMF 和 Connection Agent 流程
   - 监控计算服务状态，必要时重新编排

3. **计算服务规划**（3步）
   - 识别通信 QoS 要求和计算延迟/带宽要求
   - 基于计算资源类型选择 CMF
   - 选择 Connection Agent 协调 PDU Session

4. **资源协调流程**（10步）
   - UE → Computing Agent（via computing NAS）
   - Computing Agent → CMF（选择 Computing Node）
   - Computing Agent → Connection Agent（协调资源）
   - Connection Agent ↔ 6G SM（建立连接）
   - 返回计算服务响应
   - UE 发送计算数据
   - Computing Agent 监控状态
   - 必要时触发 Computing Node 迁移

5. **迁移策略**
   - Computing Agent 评估迁移必要性，选择目标节点
   - 基于网络状态选择迁移策略（live/cold/stateless）
   - CMF 执行迁移动作（选择节点、触发上下文迁移、更新路由规则）

---

### Solution #22.7 (计算服务授权) — 1 篇

#### S2-2606088 (Huawei, HiSilicon)
**核心贡献**: 基于 UDM 订阅数据的计算服务授权

**主要内容**:
1. **Variant A**: CCCE 授权（TBD）
2. **Variant B**: CP NF（Computing Agent 或 CMF）授权
   - 接收计算服务请求后，第一个 CN NF 基于 UDM 订阅数据进行授权
   - 如果没有订阅数据，从 UDM 获取
   - 订阅数据显示是否允许计算资源请求
   - 如果允许则接受，否则拒绝

---

### Solution #22.11 (计算资源监控) — 1 篇

#### S2-2606089 (Huawei, HiSilicon)
**核心贡献**: 计算资源状态监控的事件机制

**主要内容**:
1. **Variant A**: CMF 在 Computing Node 中设置事件
   - **报告频率**: 事件触发或周期性
   - **事件触发参数**: 报告阈值、最小等待时间
   - **事件类型**:
     - 支持的计算延迟
     - 剩余计算资源
     - 计算任务状态（如成功）
   - **触发时机**: 计算关联会话建立后
   - **触发效果**: 可能触发 Computing Node 重选

2. **Variant B**: SHE Controller 基于实现监控（TBD）

---

### 新增 NOTE — 1 篇

#### S2-2606084 (Huawei, HiSilicon)
**核心贡献**: 在 Solution Category Overview 中添加 NOTE

**主要内容**:
- 在第4组（Computing Exposure from 6G CN to AF）添加 NOTE：
  > "NOTE: Not all solutions require exposure from 6G CN to AF on computing related information or communication delay."
- 说明并非所有方案都需要从 6G CN 向 AF 暴露计算相关信息或通信延迟
- 反映 CN 控制协调方案的主要思路

---

## 四、华为技术方案核心特点

### 1. Computing Agent 架构
- **定位**: 网络侧智能代理，协调计算和通信资源
- **功能**: 意图解释、授权、流程编排、状态监控、迁移决策
- **交互**: 与 CMF（计算资源选择）和 Connection Agent（连接协调）协作
- **支持场景**: UE 请求、AF 请求、单 UE、UE 组、大规模地理区域

### 2. 计算资源描述框架
- **参考**: OpenStack 云边缘计算白皮书
- **资源类型**: Software、Infrastructure、Platform、AI Model
- **描述属性**: Computing Node ID、能力标签、容量、硬件规格、带宽、预配置服务（flavors）

### 3. 用户面协议设计
- **Computing Layer**: 新增协议层，携带任务标识和优先级信息
- **任务级协调**: 支持 Computing Node 负载均衡和调度优化
- **GTP-U 增强**: 在 UPF 和 Computing Node 之间传递计算层信息

### 4. 通算协调机制
- **会话级（控制面）**: CP NF 确定通信和计算参数
- **任务级（用户面）**: 基于 on-path 信息动态调整
- **Computing Enforcement Rule**: 类似 PCC Rule，包含计算延迟、资源类型等

### 5. 服务连续性
- **CSCP**: Computing Service Continuity Policy
- **CCCID**: Combined Communication and Computing Identifier
- **迁移策略**: live/cold/stateless，基于网络状态选择

### 6. 授权机制
- **基于 UDM 订阅**: Computing Agent/CMF 从 UDM 获取订阅数据
- **隐式授权**: 无需显式授权指示，基于订阅自动判断

### 7. 资源监控
- **事件订阅**: CMF 在 Computing Node 设置监控事件
- **触发条件**: 计算延迟、剩余资源、任务状态
- **报告方式**: 事件触发或周期性

---

## 五、与其他公司方案的对比

| 维度 | 华为方案 | 其他公司方案 |
|------|---------|-------------|
| **核心 NF** | Computing Agent + CMF + Connection Agent | CMF/CCF/CCCE 等 |
| **请求路径** | 支持 computing NAS、AF via NEF | SM NAS、UP、Service Plane 等 |
| **资源描述** | 参考 OpenStack，定义通用模板 | 各公司自定义 |
| **协议设计** | 新增 Computing Layer | GTP-U 增强或无新层 |
| **协调机制** | 会话级+任务级双层协调 | 主要会话级 |
| **服务连续性** | CSCP + CCCID + 迁移策略 | CCCID 或类似标识 |
| **授权机制** | UDM 订阅隐式授权 | PCF/CCF 策略授权 |
| **UE 组支持** | 明确支持大规模 UE 组 | 部分支持 |

---

## 六、关键技术细节

### 1. Computing Enforcement Rule 参数
`
- Computing Session ID: 标识计算会话
- Rule ID: 规则唯一标识
- Precedence: 规则优先级
- Packet filters: 包过滤器
- Computing latency: 计算延迟
- Computing resource type: 计算资源类型
`

### 2. Computing Layer 信息
`
UL 方向（UE → Computing Node）:
- Task identification information:
  - Computing task ID
  - End indication of task / Total number of payload
- Task priority & monitoring information:
  - Priority of computing task
  - Delay monitoring information (sending time)

DL 方向（Computing Node → UPF）:
- Task Identification information
- DL remaining delay budget
`

### 3. AF 计算服务请求参数
`
- AF Computing Service Session ID
- UE ID / UE group information
- Application ID
- Computing resource type (e.g., TensorFlow API)
- Overall RTT latency
- Overall bandwidth requirement
- Specification and number of xPUs (optional)
- Requested service area
- Requested service time
- Intent (optional)
`

### 4. 监控事件类型
`
- Supported computing delay
- Remaining computing resources
- Status of computing task (e.g., success)
- Computing node load (e.g., load of xPUs)
`

---

## 七、总结

华为在 SA2#175-AH-e KI#22 提交了 7 篇提案，核心贡献包括：

1. **Computing Agent 架构**: 提出网络侧智能代理，统一协调计算和通信资源
2. **通用流程描述**: 为 Solution #22.2 提供详细的通用部分（6家联合）
3. **用户面协议设计**: 新增 Computing Layer 支持任务级协调
4. **AF/UE 双场景**: 详细描述 AF 和 UE 请求场景下的完整流程
5. **授权和监控**: 基于 UDM 的隐式授权和事件驱动的资源监控
6. **服务连续性**: CSCP 策略和 CCCID 标识支持无缝迁移

华为方案的特点是强调 CN 控制、智能代理、双层协调（会话级+任务级），并参考云计算标准（OpenStack、Kubernetes）进行设计。
