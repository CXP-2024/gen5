# Topic 2 流控之二:Dimension Pool(DP,维度池)— 设计与执行计划

> 撰写时间:2026-08-27 深夜(通宵执行计划)。本文档为中文工作计划;
> 提交用的正式设计文档(英文 `dp_design.md`)在实现完成后另行撰写。
> 所有设计决策均已在 2026-08-27 的对话中与用户逐条确认锁定。

---

## 0. 一句话概括

**DP 把同一路由器上"同维度、相对方向"的两个输入口缓冲合成一个流动性池:
方向性负载下,冷方向的空闲槽借给热方向用,总存储不变;安全性完全不依赖池,
而由可插拔的"安全基座"(CBS 专用子环,或 escape VC)独立保证。**

PCN 对应:一条双向支付通道的两侧余额本质上是一个资金池;单向流量把一侧
打满时,允许"超额透支对侧闲置流动性"(shared tranche),但每侧保留一笔
**不可外借的准备金**(dedicated tranche / escape floor)保证任何时候都能
完成最低限度的清算(即死锁自由)。速率 = 流动性 / RTT(Little 定律),
与 HTLC in-flight 限额同构。

## 1. 锁定的设计决策(用户确认,不再改动)

| 决策 | 内容 |
|---|---|
| 机制 | 只做 DP 主体(计数式共享池),不做 CCA;不做浮动准备金 |
| 变体一 DP-CBS | 算法 3(DOR)+ CBS 基座,**r = 2** 固定;等存储对比 vcs = 3、4 基线 |
| 变体二 DP-ESC | 算法 4(自适应)+ escape 基座,**escape 层 = 1 条 VC(即 r = 1)**;等存储对比 vcs = 2、3、4 基线 |
| 范围外 | 方向翻转 / 再平衡时延实验(明确移出本期);包的物理搬移(池是纯记账,包不挪) |
| 叙事 | 一个池机制 × 两个可插拔安全基座 = 流控层(Topic 2)与路由层(Topic 1)的组合展示 |

## 2. 形式化机制

### 2.1 池的定义

设路由器 R、维度 d ∈ {X, Y, Z}、控制 vnet v。池 P(R, d, v) 覆盖 R 上
维度 d 的**两个相对输入口**(East+West / North+South / Up+Down)在 vnet v
的缓冲槽。Local(NI 注入/弹出)口不入池。控制 vnet 中
`buffers_per_ctrl_vc = 1`,故 **槽 = VC = 单飞包**。

每个输入口配置 V 条物理 VC(`--vcs-per-vnet`),按 **VC 编号**切成两段
(编号固定,不按计数漂移——这是安全论证成立的关键,见 §3):

- **DP-CBS**(算法 3):专用段 = 编号 `[0, r)`(r = 2),池化段 = 编号 `[r, V)`;
- **DP-ESC**(算法 4):池化段 = 自适应类 = 编号 `[0, V − escape_vcs)`,
  豁免段 = escape 类 = 编号 `[V − escape_vcs, V)`(沿用队友的
  "escape 为每 vnet 最后 escape_vcs 条"的既有约定)。

### 2.2 准入规则

记 `shared_used(P)` = 池 P 两个输入口上**池化段**中非空闲 VC 的总数,
S = `--dp-shared-cap`(池容量上限)。

1. **池化段准入**:上游分配一条池化段 VC,要求 `shared_used(P) < S`。
   这是纯性能策略,**永不参与安全论证**。
2. **专用段准入(DP-CBS)**:专用段 `[0, r)` 构成每个有向环上一个深度为
   r = 2 的**私有子环**,其上原样运行 CBS:
   - *入环规则*:入环包(注入或换维)且下游输入口持有 critical-bubble
     标记时,要求下游**专用段**空闲 ≥ 2;
   - *环内位移规则*:环内直行包可以填掉标记口专用段的最后一个空槽,
     但**仅当它自己正住在专用段 VC 里**(腾出的必须也是专用槽),
     此时标记上移到它腾出的槽位。住在池化段 VC 里的直行包不得填最后
     一个专用空槽(它可走池化段,若池未满)。
3. **豁免段准入(DP-ESC)**:escape VC 分配完全不查池(Duato 基座)。
   路由决策层(`outportCompute3DAdaptive`)把"池已满"视同"该出口
   自适应类不可用"而跳过该候选——池满时包**自然回退到 escape**,
   这是防止池锁死的关键挂点(见 §3.3)。
4. **分配偏好**:DP-CBS 下优先池化段、专用段兜底(先花池信用、后动
   准备金,与 PCN 语义一致,同时最大化 bubble 流动性)。

### 2.3 记账实现(零搬移、零时延)

全局注册表 `m_dp_shared_occ[router][dirn6][vnet]`(挂在 GarnetNetwork,
与 CBS 标记注册表同样的"全局单一事实来源"手法):

- **加一**:上游 `SwitchAllocator::vc_allocate` 选中池化段 VC 时
  (授予即预约,与 credit 视图同步,保守不漏记);
- **减一**:上游 `OutputUnit::wakeup` 收到 `is_free_signal` credit、
  该 VC 属池化段时(释放经 credit 延迟可见,保守)。

同一条链路的加/减都发生在上游侧,天然配对。gem5 事件顺序执行,同拍内
两个上游路由器先后查表,后者看得到前者的加一——不会超发。硬件实现说明
(写入报告):池计数等价于下游路由器向两个上游邻居发放的 S 张共享信用票,
随既有 credit 通路捎带(piggyback),1 拍陈旧性无害——池只影响性能不影响安全。

## 3. 安全论证(报告核心,含反例)

### 3.1 天真的"保底"为什么错(必须写进报告的反例)

若只规定"每口占用可超 r、但两口之和 ≤ 池容量 C",取 C = 8、r = 2、V = 8:
某 X 环上每个路由器 East、West 口各占 4(和 = 8 = C,处处封池;各口占用
均 ≥ r,保底不起作用)。两个方向的环内包互相等待对方腾槽:East 向包要
West 侧减员才开池,West 向包要 East 侧减员——**跨方向循环等待,物理上
明明还有空 VC 却全网冻结**。教训:**池容量上限绝不能出现在安全路径上**;
安全必须由一个**准入不查池状态**的子结构独立保证。

### 3.2 DP-CBS 的安全构造("深度域 Duato")

专用段(每口 VC 0..1)在每个有向环上构成一个 2 深私有子环,其准入
规则(§2.2 第 2 条)完全不读池状态。论证:

- **不变量**:每个有向环、每个 ctrl vnet,专用段空槽总数 ≥ 1(标记所在)。
  入环受"标记口需 2 空"保护;环内直行填最后一个专用空槽时,规则强制
  搬运者自己住专用段——它腾出的也是专用槽,空槽守恒,标记随之上移。
  若允许住在池化段的直行包填最后一个专用空槽(它腾出的是池化槽),
  不变量即被打破——这就是 §2.2 中"仅当住在专用段"条款的由来。
- **不变量 ⇒ 可排空**:设标记在口 X(专用空 ≥ 1),上游口 Y。若环上
  专用空槽仅剩 X 这一个,则 Y 的专用段必满、必有专用段住户:该住户若
  直行,规则允许其填 X 的最后专用空槽(标记上移),环前进;若其要
  换维/弹出,则按 DOR 严格降维归纳(Z 环无出环转向必排空 → Y → X),
  它终将离开、Y 腾出专用槽。若环上专用空槽多于一个,则存在未标记口
  或 2 空标记口,池化段住户也可按入环规则转入专用段(相当于 Duato
  的"随时可上逃生道")。轮转仲裁的弱公平性保证等待者最终中签。
- **r = 2 的必要性**:CBS 需要"紧邻标记的入环点凑齐 2 个空槽"才可能
  前进——正是既有实现里 `--enable-cbs 要求 vcs ≥ 2` 的 fatal_if 教训;
  专用段深度 2 是 CBS 基座的最小值,也是用户锁定值。
- **证明复用**:该论证与已提交的 vcs = 2 纯 CBS 证明逐字同构,只是
  论域从"整个 vnet 的 VC"缩小到"专用段窗口 [0, 2)"。

### 3.3 DP-ESC 的安全构造(Duato 原样)

escape VC 走 Mesh3D XYZ 路由(无环绕,信道依赖图无环),分配豁免池检查;
自适应类哪怕全部被池封死,`outportCompute3DAdaptive` 会因"候选不可用"
回退 escape(实现上把"池满"并入候选过滤条件,见 §4 RoutingUnit 改动,
这是本变体唯一的安全关键改动点——若只在 send_allowed 里拦,路由层会
反复选择"看似有空 VC 但池满"的自适应候选,包被无限期挂起,escape 永远
得不到尝试,Duato 前提被破坏)。证明即队友 Topic 1 的 Duato 论证原文。
注意:**环路由的 escape 会死锁**(有向环依赖闭合),Mesh 路由的 escape
才成立——报告里要点名这一区别。

### 3.4 诚实声明

池上限的瞬时超越(硬件 1 拍陈旧性)与池满引发的暂时绕行都只影响性能
曲线;两变体的死锁自由分别由 §3.2 / §3.3 独立成立,与 S 取值无关。

## 4. 实现方案(最小侵入,全部由 `--enable-dp` 门控)

| 文件 | 改动 |
|---|---|
| `GarnetNetwork.py` | `enable_dp`(Bool)、`dp_reserve`(UInt32,缺省 2)、`dp_shared_cap`(UInt32,缺省 0) |
| `configs/network/Network.py` | `--enable-dp / --dp-reserve / --dp-shared-cap` 及透传 |
| `GarnetNetwork.hh/.cc` | 参数读取;`dpInit()` 清零注册表;`isDPEnabled/getDPReserve/getDPSharedCap`;`dpGoverns(vnet)`(ctrl vnet 且开关开);`dpPooledOffset(offset)`(按算法 3/4 给出池化窗口判定);`dpSharedUsed(down_router, dirn)`(两口求和,方向索引复用 cbsDirnIndex,配对即 `idx^1`);`dpNoteAlloc/dpNoteFree`;统计 `dp_pool_blocks / dp_shared_grants`;新增 fatal_if 组(见下) |
| `OutputUnit.cc` | `wakeup()` 收到 free-signal credit 时一行调用 `dpNoteFree(上游路由器, m_direction, vc)` |
| `SwitchAllocator.cc/.hh` | ① `send_allowed` 非自适应分支:DP 开启时改为"池化段可用(有空 VC 且池未满)∥ 专用段可用(CBS 规则限定在窗口 [0, r),含'池化段住户不得填最后专用空槽'新条款)";② 自适应分支:非 escape 请求加池检查(保险带);③ `vc_allocate`:算法 3 下按偏好选窗口(池化优先、专用兜底),选中池化段则 `dpNoteAlloc` + `dp_shared_grants++`;算法 4 沿用类窗口选择,非 escape 选中后 `dpNoteAlloc`;④ 环内位移规则改用专用窗口空槽数(`free_vc_credit_count(vnet, 0, r) == 0` 且 `outvc` 落在专用段)判定 |
| `RoutingUnit.cc` | `outportCompute3DAdaptive` 候选过滤:`require_available` 时"池满"的出口按不可用跳过(自然回退 escape) |

**fatal_if 组**(GarnetNetwork::init):需 torus 维度非零;不可与
`--wormhole` 同用;算法必须为 3 或 4;算法 3 时必须 `--enable-cbs`、
`dp_reserve ≥ 2`、`vcs > dp_reserve`、`1 ≤ dp_shared_cap ≤ 2·(vcs − dp_reserve)`;
算法 4 时必须 `escape_vcs ≥ 1`、`1 ≤ dp_shared_cap ≤ 2·(vcs − escape_vcs)`。

**不改的地方**:NI 注入(Local 口不入池,`NetworkInterface.cc:463` 的
"NI 只注自适应类"约定原样);CBS 关闭 DP 时的全部既有行为(窗口退化为
整个 vnet);队友算法 4 在 DP 关闭时的全部行为。

## 5. 实验矩阵(等真实存储对比)

平台:4×4×4 Torus3D,64 CPU,`--inj-vnet=0`,10k 周期,注入率
0.05–1.00 步长 0.05,8 并行任务,脚本 `run_sweep_dp.py`(结构沿用
topic2 版:断点续跑、死锁 panic 记为数据)。

**等存储原则**:DP 配置的"每维度对真实总槽数 C"与其基线相同;
DP 的 V 取到"热方向可吃满整个池"(V = r + S 或 V = S + escape)。

| 组 | 配置 | 参数 | C(对/vnet) |
|---|---|---|---|
| A1 | CBS 基线 | 算法3+CBS,vcs=3 | 6 |
| A2 | **DP-CBS** | 算法3+CBS+DP,vcs=4,r=2,S=2 | 6 |
| A3 | CBS 基线 | 算法3+CBS,vcs=4 | 8 |
| A4 | **DP-CBS** | 算法3+CBS+DP,vcs=6,r=2,S=4 | 8 |
| B1 | 自适应基线 | 算法4,vcs=2(escape 1) | 4 |
| B2 | **DP-ESC** | 算法4+DP,vcs=3,escape 1,S=2 | 4 |
| B3 | 自适应基线 | 算法4,vcs=3 | 6 |
| B4 | **DP-ESC** | 算法4+DP,vcs=5,escape 1,S=4 | 6 |
| B5 | 自适应基线 | 算法4,vcs=4 | 8 |
| B6 | **DP-ESC** | 算法4+DP,vcs=7,escape 1,S=6 | 8 |

流量 5 种:`uniform_random / torus3d_neighbor / torus3d_tornado /
torus3d_transpose / torus3d_xopposite`。共 10 × 5 × 20 = 1000 点,
按优先级分批跑(xopposite、tornado、transpose 先行)。

**为什么 xopposite 是 DP-CBS 的头牌流量**(今晚代码阅读的关键发现):
`torus3d_xopposite` 的目的地为 +X/2(4 环上 +2 跳);算法 3 的
`shortestDirection` 在等距时**取正向**——因此该流量在 DOR 下纯东向,
每条东向链路承载 2 条流(需求 = 2×注入率,最高到满线速),西向口全程
空置:池的可借出资产最大、且需求恰好压在窗口极限上。Little 定律预测:
A1(热方向窗口 3,credit RTT≈4)在净周期线速 ~0.75 处失稳,A2(窗口
可达 4)应显著推后。注意算法 4 下 xopposite 等距双候选、自适应会双向
分流,故它同时是 B 组"路由已均衡时池增益归零"的对照。

**DP-ESC 的头牌是 neighbor / tornado(各维 +1,单向)**:B1 的自适应
类每口仅 1 条 VC(窗口 1 → 上限 ~0.25–0.33 净线速 < 0.5 的最大供给),
必然饱和;B2 池允许热方向占满 2 条 → 预期解除饱和。B5/B6 预期归零
(诚实的剩余机制检验:瞬态突发吸收/溢出遏制)。uniform 对称,
预期全组 ≡ 基线(设计上的零开销声明)。transpose 检验热点遏制。

**死锁探针**(200k 周期、rate 1.0):A2/A4 × {transpose, xopposite},
B2 × {transpose, xopposite}。预期零死锁;CBS 深拥塞下已知 ~1.6% 入环
节流为既有现象。

**T_hold 标定**:不写新代码,由基线饱和点反推(T_hold = N/rate_sat),
与 credit RTT 3–4 拍的结构分析对照,写入报告。

## 6. 新增统计量

- `dp_pool_blocks`:仅因池满被拒的准入次数(分变体路径累加);
- `dp_shared_grants`:池化段成功分配次数(借贷发生量);
- 既有 `cbs_entry_blocks / cbs_mark_moves`(A 组)与
  `escape_hops / escape_transitions`(B 组)照常采集,
  验证机制确在工作(如 B2 池满时 escape_transitions 应上升)。

## 7. 今晚执行顺序

1. ✅ 读透源码(SA / OutputUnit / RoutingUnit / GarnetNetwork / 流量模式);
2. 本文档;
3. 实现 §4(Windows 侧 `gen5/` 编辑);
4. 桥接 WSL(Copy-Item + `sed -i 's/\r$//'`)→ `scons build/NULL/gem5.opt PROTOCOL=Garnet_standalone -j$(nproc)`;
5. 冒烟:每条 fatal_if 路径 + A2/B2 低载短跑(校验 dp 计数动、无死锁、
   uniform 下曲线与基线重合);
6. `run_sweep_dp.py` 分批跑 1000 点 + 4 个死锁探针;
7. 期间撰写英文 `dp_design.md`(正式提交文档);
8. 收结果、`plot_results_dp.py` 出图、`summary_dp.csv`、中文晨报。

## 8. 风险与对策

- **单点风险:算法 3 的 vc_allocate 偏好与 send_allowed 判定不一致**
  → 两处共用同一个窗口选择助手函数,消灭分叉;
- **池计数漂移**(加减不配对)→ 冒烟阶段在 sim 结束时断言注册表归零
  (drain 后应无占用;若不便断言,则以低载长跑 dp_shared_grants 与
  free 事件对账);
- **1000 点跑不完** → 分批+断点续跑,优先 xopposite/tornado/transpose;
  uniform/neighbor 可降为步长 0.1;
- **xopposite 在算法 4 下双向分流导致 B 组无单向压力** → B 组头牌
  已改用 neighbor/tornado(单一最短方向,自适应也只能走一边)。
