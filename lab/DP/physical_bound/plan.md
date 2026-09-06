# DP-Phys 实现计划

**日期**：2026-09-06
**依据**：`design.md` v5
**修订**：v5 对齐——**撤销 RTS 与一切"≡ PRIV 位级"验收**（无归还的 RTS 是静态
配置不是策略，见 §4.2/Q10），首批三臂 PRIV/RR/STARVE，矩阵 1400→1000；
统一验收 harness；M5 传输改借道反向 CreditLink；新增授予腿超订检查
**基线**：`~/gem5` @ `a89b079`（stage-1/2 快照）之上重写
**产物**：`build/NULL/gem5.opt`，`PROTOCOL=Garnet_standalone`

---

## 0. 贯穿全程的两条纪律

**纪律 A：单一验收 harness，全程只有这一把尺子。** 硬门只有两类：
① **PRIV 自身位级不变**——PRIV 从不进入 DP-Phys 代码路径，任何重构后它必须与
重构前逐位一致（这是"改动没碰既有路径"的自证，与新机制无关）；
② **机制完整性不变量**（design v5 P1）——`g_E+g_W==P`、per-IU `≤ r+P/2`、
无非法跨 IU 落槽、无死锁、`B_pair=8` 恒定、Local 口钉死为基线 `v` 个 id。
后两条（等硬件/等预算）是全部增益归因的前提，破了则数据无意义。
**不允许每个里程碑各造一套检查。**

统一为一个脚本 `research/regress.py`，唯一入口、唯一 diff 引擎（跑 `gem5.opt`
→ 收 `stats.txt` → 与基准逐位 `diff` 或断言检查），用 `--scope` 选规模：

| `--scope` | 内容 | 基准/判据 | 用在 |
|---|---|---|---|
| `priv` | PRIV 5 配置 | 上一次通过的自身输出，逐位 diff | M0–M3 每次改动 |
| `cbs` | `--routing-algorithm=3 --enable-cbs` 3 配置 | 快照 `a89b079`，逐位 diff | M0 |
| `static-smoke` | `--dpphys-policy=static`（不迁移），1 流量 × 3 速率 | 跑通 + 全部不变量 + 与 PRIV 曲线**接近**（诊断信号，非硬门） | M2、M3 |
| `invariant` | 断言跑（P1 六条不变量） | 断言零触发 | M3–M7 |

`static-smoke` 里"与 PRIV 接近"只是**诊断**：static 是冻结的 50/50 划分，与
PRIV 资源逐槽相等，大幅偏离几乎必是编号/迭代序 bug——但不把"位级相等"设为
公理（那是 v4 的错误）。**M1 之前先建 harness。**

**纪律 B：机制改动与策略改动分离提交。** M1–M3 只搬结构、不引入任何新行为，
它们的硬门全部是"PRIV 位级不变 + 不变量零触发"。真正的行为从 M4 才开始。

---

## 关键简化：所有权由 credit 本身承载

读代码时确认的一点，可显著收缩 M3：

`OutputUnit::outVcState[vc]` 就是"上游对下游某个 VC 的持有凭证"，而 credit 是
沿**本侧**的 `CreditLink` 单向送回上游的。因此在 pair-global 编号下：

> **池 id `x` 归 `f` 侧** ⟺ **`x` 的 credit 当前在 `f` 侧上游手里。**

授予不需要广播，也不需要上下游共享一张表——授予就是**在释放点选择向哪一侧
`InputUnit::increment_credit(x, ...)`**，credit 自己走到那一侧的上游，凭证随之
转移。这与 §4.1 的"发送 = 释放 = 授予、同一处代码、`U ≈ 0`"精确吻合。

下游 R 侧仍需一张 `PoolOwner[P]`，但**只为 STARVE 计算 `free_f`**，不参与安全，
错了也只是策略变差、不会破坏正确性。这把"分布式一致性问题"降级为"本地统计"。

推论：**pair-global 编号（M2）是整个设计能成立的唯一前提**，因为上游必须能在
链路上命名对侧 IU 的物理槽 id。M2 失败则设计不可实现，无绕路。

---

## 里程碑

```mermaid
graph LR
  M0[M0 清除旧 DP] --> M1[M1 逃逸谓词化]
  M1 --> M2[M2 pair-global 编号]
  M2 --> M3[M3 所有权+跨IU落槽<br/>默认=static 不迁移]
  M3 -->|不变量验收| M4[M4 STARVE 授予]
  M4 --> M5[M5 归还通道]
  M5 --> M6[M6 RR + 旗标 + 统计]
  M6 --> M7[M7 1000 次实验]
```

---

### M0 — 清除旧 DP（结构，无行为）

**目标**：把阶段1/2 的 DP 机制整体摘除，留下干净的 CBS + 自适应路由基座。

**范围**：只删 **DP**，**保留 CBS**——CBS 是 Lab3/topic2 的独立机制、也是
algorithm 3 的基座，与 DP-Phys 不冲突。

**改动**：

- `GarnetNetwork.{hh,cc,py}`：删 `m_enable_dp / m_dp_reserve / m_dp_shared_cap`、
  `isDPEnabled / getDPReserve / getDPSharedCap / dpGoverns / dpPooledOffset /
  dpSharedUsed / dpPoolFull / dpNoteAlloc / dpNoteFree / dpInit`、
  `m_dp_shared_occ`、统计 `dp_pool_blocks / dp_shared_grants`，以及构造函数中
  的 DP 校验块（`GarnetNetwork.cc:163-202`）。
- `SwitchAllocator.cc`：删 `vc_allocate` 中的 DP 分支与 `dp_cbs_admission`，
  **CBS 气泡位移逻辑回退为纯 CBS**（这是唯一需要动脑的一处）。
- `OutputUnit.cc::wakeup`：删 `dpNoteFree` 块。
- `RoutingUnit.cc`：删"跳过下游池已满的 outport"钩子。
- `configs/network/Network.py`：删 `--enable-dp / --dp-reserve / --dp-shared-cap`
  及其 `init_network` 赋值。

**验收**：

1. `scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j$(nproc)` 通过。
2. `regress.py --scope=priv` 全绿（PRIV 从不经过 DP 分支，必须逐位不变）。
3. `regress.py --scope=cbs` 全绿——与快照 `a89b079` 逐位一致。
   这条是 M0 唯一的真风险点。

**风险**：`dp_cbs_admission` 与 CBS 标记逻辑纠缠，回退时可能改变 CBS 行为。
缓解：用 `git show a89b079:...SwitchAllocator.cc` 对照，逐个 DP 条件按
"DP 关闭"路径求值化简，而不是重写。

---

### M1 — 逃逸 VC 谓词化（结构，无行为）

**目标**：消灭"逃逸 = 最高 k 个 id"这个散布 9 处的隐式约定，为 M2 让路。

**改动**：在 `GarnetNetwork` 上新增三个查询，替换全部 9 处裸算术：

| 新 API | 语义 | 替换点 |
|---|---|---|
| `isEscapeVC(vc)` | 该 vc 是否属逃逸类 | `RoutingUnit.cc:392,507`、`SwitchAllocator.cc:152,256`、`NetworkInterface.cc:463` |
| `escapeWindow(vnet)` → `(offset,count)` | 逃逸类的选择域 | `RoutingUnit.cc:424`、`SwitchAllocator.cc:483,601` |
| `adaptiveWindow(vnet)` → `(offset,count)` | 自适应类的选择域 | 同上 + `GarnetNetwork.cc:196,372` |

M1 内三者的实现**与现约定完全等价**（`offset = V - escape_vcs` 等），不改语义。

**验收**：`regress.py --scope=priv` 与 `--scope=cbs` 全绿。这是纯重构，
**任何 diff 都是 bug**。

**为何单独成一步**：它是全流程唯一一个"可以被完全证伪"的机械步骤；把它和 M2
混在一起，M2 出问题时无法区分是重构错了还是编号方案错了。

---

### M2 — pair-global 编号空间（结构，行为需保持）

**目标**：让上游能在链路上命名对侧 IU 的物理槽（见"关键简化"）。

**布局**（`r=2, P=4, escape_vcs=1`，`vcs_per_vnet = 2r+P = 8`）：

| id | 物理 IU | 类 | 静态归属 |
|---|---|---|---|
| 0 | E-IU | 自适应保留 | E（永久） |
| 1 | E-IU | **逃逸保留** | E（永久） |
| 2 | W-IU | 自适应保留 | W（永久） |
| 3 | W-IU | **逃逸保留** | W（永久） |
| 4,5 | E-IU | 池 | 可迁移 |
| 6,7 | W-IU | 池 | 可迁移 |

**改动**：

- 新增 `DPPhysLayout`（建议放 `GarnetNetwork` 内或单独小头文件）：
  `idToIU(id)`、`reserveOf(side)`、`poolIds()`、`isEscapeVC(id)`（覆写 M1 的
  实现）、`ownedAdaptiveOrdered(side)`、`ownedEscapeOrdered(side)`。
- `OutputUnit` 新增**掩码版**选择器
  `select_free_vc_masked(vnet, const VcMask&)` /
  `free_vc_credit_count_masked(vnet, const VcMask&)`，
  与现有连续窗口版并存（PRIV 路径继续走旧版）。
- **Local 口钉死**：`NetworkInterface` 与 Local `InputUnit` 的可用 id 集固定为
  基线 `v` 个（`0..v-1`）。**不做这条，注入缓冲翻倍、等预算前提静默破裂**，
  之后任何增益都无法归因（P1 不变量⑥）。
- 断言：每 IU 活跃 VC 数 `≤ r + P/2`（`gem5_assert`，非 fast build 生效）。

**工程要求（顺序保持）**：掩码迭代必须**先自适应类、后逃逸类**，且类内保持
升序。这样 static 下 E 的可用序 `{0,4,5} → {1}` 与基线 `{0,1,2} → {3}` 结构
对应，SA 的 round-robin 环序也对应（未用槽恒为 IDLE，指针扫过即跳过）。
这不再是公理（v4 曾把它抬成位级恒等的前提），但仍然要做：它让 static-smoke
的诊断信号有效，也避免仲裁序引入与策略无关的噪声。

**验收**：

1. `regress.py --scope=priv` 全绿（PRIV 走 `vcs-per-vnet=4` 旧路径，
   必须完全不受影响）。
2. `regress.py --scope=static-smoke`：`--dpphys-policy=static --dpphys-r=2`
   （静态 50/50 + 重编号，无迁移）跑通、六条不变量零触发。诊断信号：曲线应
   与 PRIV 接近，大幅偏离先查编号/迭代序。
   **M2 一做完立刻跑这条，不要等到 M3**——M2 仍是全流程的生死点：pair-global
   编号不成立则上游无法命名对侧 IU 的槽，设计不可实现。

**风险（最高）**：编号/迭代序出错的表现是 static-smoke 大幅偏离 PRIV 或断言
触发。诊断路径：把 stats diff 收窄到单路由器单 VC 的 `buffer_reads` 计数。
短期定位不了则走文末回退方案。

---

### M3 — 所有权表 + 跨 IU 落槽（机制成型，默认 static 不迁移）

**目标**：打通物理共享的数据通路，默认策略为 **static**（不迁移），
用不变量而非位级恒等验收。

**改动**：

- `InputUnit` 新增 `void depositFlit(int vc, flit *t_flit)`：完成
  `set_vc_active / grant_outport / insertFlit` 与 buffer-write 统计。
  （`virtualChannels` 私有，这是 V1 结论要求的唯一新访问器。）
- `InputUnit::wakeup`：若 `idToIU(vc) != m_id`，改调
  `m_router->getInputUnit(idToIU(vc))->depositFlit(vc, t_flit)`；
  路由仍按**真实入口方向**算（2 bit tag，§6.5——仅为 credit 转向与统计）。
- `Router` 新增每维度对的 `PoolOwner[P]`（3 对 × P 项）。
- `SwitchAllocator::arbitrate_outports` 的 3 处 `increment_credit`：抽出
  `grantOnRelease(inport, vc)`，static 下恒等于"还给原侧"。

**验收**：

1. `regress.py --scope=priv` 全绿（PRIV 路径仍不受影响）。
2. `regress.py --scope=static-smoke` + `--scope=invariant` 全绿，
   且 static 下 `dpphys_grants_migrated == 0`（通路存在但未走）。
3. **强制迁移冒烟**：`--dpphys-policy=forced`（永远授予对侧）跑通 1 个配置、
   确认不崩不死锁、`dpphys_grants_migrated > 0`——static 下跨 IU 落槽路径
   不会被触发，必须用 forced 把它点亮一次，否则 M3 交付的是没测过的代码。
   仅作冒烟，不进实验矩阵。

---

### M4 — STARVE 授予策略（第一次真行为）

**改动**：`grantOnRelease` 实现 §4.3 规则——在释放事件上、以**排除刚释放槽**的
状态求值，`free_f` = `f` 侧拥有且空闲的槽数（含保留区；Q4 首批**不排除逃逸**）：

```
both free_E==0 且 free_W==0  -> RR（1 bit 轮转）
free_E == 0                  -> E
free_W == 0                  -> W
both > 0                     -> RR
```

**新增前提检查：CreditLink 不得被授予腿压垮。**
`CreditLink : public NetworkLink`，`NetworkLink::wakeup()` **每周期只搬一枚**。
基线下一个 IU 一个读口 → 至多 1 flit/cycle → 1 credit/cycle，**恰好卡满、零余量**。
STARVE 下若一侧持续饥饿，两个 IU 的释放会**全部**导向同一条 credit link →
峰值 2/cycle → `creditQueue` 积压 → 授予被延迟 → **§4.1 的 `U ≈ 0` / Δ=0 失效**，
而那是"授予不比传统 credit 返还慢"这一主张的支点。
结构上它只在 pair 释放率 > 1/cycle 时咬人：C1 区（`L=8`）天花板
≈0.35 flit/cycle/inport、pair ≈0.7，**够不着**；可能触发的是 `L=1` 近饱和，
即不主张增益的对照臂。**因此这必须测量而非假设**：加统计
`dpphys_grant_queue_depth`（`creditQueue` 深度峰值/均值）。

**验收**：

- `dpphys_grants_migrated > 0`（机制真的启用）。
- `g_E + g_W == P` 不变量断言全程成立。
- P6 冒烟：`L=8` tornado 满载 10k 周期无死锁。
- **`dpphys_grant_queue_depth` 在 `L=8` 全程 ≤ 1** —— 成立则 `U ≈ 0` 可写进报告；
  不成立则如实降级 §4.1 的主张，不得掩盖。
- **尚不期待增益**：无归还通道时 STARVE 在 tornado 下应退化到接近静态 50/50
  （§4.4 的结构性缺陷：迁移速率 ∝ 对向流量）。
  **若此时就出现大幅增益，说明有归因错误，先查。**

---

### M5 — 归还通道（承重件）

**改动**：

- **上游侧触发**：`OutputUnit` 每周期求值 `credits_held > flits_queued`；
  `flits_queued(d)` = 本路由器全部输入 VC 中 `state==ACTIVE_ && outport==d`
  的条数（`Router::countFlitsFor(d)`，7×8 扫描，仿真开销可忽略）。
  条件连续成立 `T(g)` 周期则归还一枚**最高 id 的**池 credit；
  任一周期 `flits_queued >= credits_held` 清零计时器。
- **阶梯**：`g_f >= 2 → T = RTT/4`；`g_f == 1 → T = 2·RTT`（§4.4，域 `{2,1}`）。
- **传输：借道反向 CreditLink，零新增线**（源码核查更正，见下）。归还方向是
  上游→下游，本侧 credit link 方向相反不可用；但**上游路由器同一维度对的
  另一侧 out 口另有一条 credit link，方向恰好是上游→下游**（它服务反向数据流）。
  路径：`N_E` 的 W-out 决定归还 → 交给同一路由器 `N_E` 的 **W-in** 的
  `creditQueue` → 走既有 `CreditLink N_E→B` → `B` 的 **E-out** 消费时按标志位
  解复用 → 交给 `B` 的 **E-in** 作合成释放事件。
  代价仅为 credit 多 1 bit（`is_return`）+ 两端路由器内交接，**不碰数据链路**。
- `handleReturn(vc)`：不入队、不占槽，作为**合成释放事件**喂给 `grantOnRelease`。
- **归还只接 STARVE**：余量条件本身是需求信号，接到 RR 上会污染对照
  （design §4.4）；static 不迁移、无归还可言。三臂由此在同一自变量上排开。

**验收**：

- `regress.py --scope=priv` 与 `--scope=invariant` 全绿。
- `dpphys_credits_returned > 0` 且 tornado 下 STARVE 相对 M4 出现可测改善。
- 归还不得引发 `g_f < 0` 或 `g_E + g_W != P`（断言）。

**风险（已降级）**：原以为归还会抢数据链路带宽——**核查后不成立**。
`CreditLink : public NetworkLink`（`CreditLink.hh:46`，无 `.cc`），每个端口的
credit link 是**独立 NetworkLink、自带 1 flit/cycle 带宽**，与数据链路物理分离
（`Router::addInPort` 数据走 `in_link`、credit 走
`credit_link->setSourceQueue(input_unit->getCreditQueue())`）。且归还域为 `{2,1}`，
一侧一个空闲期最多归还 2 枚、`g=0` 后停止——**是瞬态事件而非稳态流**。
残余风险仅为借道那条 credit link 的复用冲突：加统计
`dpphys_return_credit_conflicts`，若非零则在报告中如实说明排队延迟。

---

### M6 — RR 策略、旗标、统计（已完成）

**改动**：

- `--dpphys-policy={static,rr,starve,forced}`、`--dpphys-r`、`--dpphys-cap`、
  `--dpphys-return-base`、`--dpphys-return-t1`（`inf` 合法，为 P5 敏感性曲线
  的端点——最后一枚永不归还）。
- 统计：`dpphys_grants_migrated`、`dpphys_credits_returned`、
  `dpphys_pool_full_blocks`、`dpphys_borrowed_peak`、
  `dpphys_grant_queue_depth`（M4 引入）、`dpphys_return_credit_conflicts`
  （M5 引入）、**分方向接收吞吐**。

**验收**：P3 的方向性——`L=8` tornado 下 `RR < PRIV`（棘轮效应，§4.2）。
**RR 若不劣于 PRIV，§4.2 的推导有误，回去改文档而不是改代码。**

---

### M7 — 实验（`design.md` §7，执行中）

5 模式（PRIV / RR-a / STV-a / RR-b / STV-b）× `L∈{1,8}` × 5 流量 × 20 速率 =
**1000 次**。使用可断点续跑的 `research/run_dpphys.py`，并由
`research/analyze_dpphys.py` 生成饱和吞吐、matched-load 延迟、方向公平性与机制
统计摘要。旧的 `run_sweep_physical.py` / `analyze_physical.py` 保留为前一阶段的
等物理存储实验记录。
全程开 `--scope=invariant` 的断言集；任何一条 P1 不变量触发即停，先查再跑
——不变量破了，其余数据无意义。

---

## 风险与回退

| 风险 | 触发信号 | 回退 |
|---|---|---|
| M2 编号/迭代序有 bug | static-smoke 大幅偏离 PRIV 或断言触发 | 让掩码迭代序**显式**映射到基线序（查表而非算术），代价是多一张 8 项表 |
| pair-global 编号整体不可行 | M2 迟迟无法通过 static-smoke | 退到 `vcs_per_vnet=4` + flit/credit 加 1 bit 侧标（Q7 的替代方案），侵入 `outVcState` 索引，工作量翻倍但机制不变 |
| M0 破坏 CBS | CBS-only 回归有 diff | 逐条 DP 条件按"关闭"求值化简，勿重写 |
| **授予腿把 CreditLink 压到 2×** | `dpphys_grant_queue_depth > 1` | 结构上只在 `L=1` 近饱和触发（非增益臂）；如实报告并降级 §4.1 的 `U≈0` 主张，**不得掩盖** |
| 归还借道的 credit link 冲突 | `dpphys_return_credit_conflicts > 0` | 报告排队延迟；归还是 `{2,1}` 域内的瞬态，预期可忽略 |

**不可回退的红线**：P1 六条机制完整性不变量（design v5 §7）——尤其
`B_pair=8` 恒定与 Local 口钉死这两条**等预算前提**。它们破了，三臂比较就不是
等硬件比较，全部增益归因失效。**这组不变量是唯一必须硬保的验收。**

---

## 开放项（进入实现后按里程碑关闭）

- **Q3** `L=8` 的 `sim-cycles`/预热 → M7 首跑后按延迟收敛曲线定。
- **Q4** `free_f` 是否排除逃逸 → M4 取"不排除"，排除版作 M6 敏感性。
- **Q5** 写口无损性取池区双写口 → M3 实现，在 §5 代价中声明面积。
- **Q10** RTS 作为真策略的归还规则设计 → **首批不做**（design v5 §4.2）；
  若后续做，需要独立的设计讨论，不复用 STARVE 的余量条件。
