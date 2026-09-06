# Topic 2 流控之一:Critical Bubble Scheme(CBS)

> Lab4 Topic 2(流控)第一项:在 Topic 1 的 Torus3D 拓扑上实现 **Critical Bubble Scheme**
> (Chen, Wang & Pinkston, *Critical Bubble Scheme: An Efficient Implementation of
> Globally-Aware Network Flow Control*, IPDPS 2011),使**无保护的 DOR 路由(算法 3)**
> 在环绕(wraparound)链路存在的 torus 上做到**构造性无死锁**,且不划分任何 VC。

## 1. 背景与动机

Torus 的环绕链路使每个方向环成为一个依赖环:维序路由(DOR)本身无法排除
"环上所有缓冲全满、彼此循环等待"的死锁。Topic 1 用 **escape VC(Duato)** 解决
该问题,但代价是把每 vnet 的 4 条 VC 划分为 3 条自适应 + 1 条逃逸,逃逸 VC 平时
利用率低。**Bubble 类流控**走另一条路:不划分通道,而是维持一个全局不变量——
**每个有向环上至少保留一个空缓冲槽(bubble)**。只要环不可能被填满,循环等待
就不可能闭合。

经典 Bubble Flow Control(BFC)要求"入环时下游至少 2 个空槽",判断是**局部**的,
每个入环点都要保守让步。CBS 的改进是把"必须保留的那一个空槽"**显式标记**出来
(critical bubble),让它像令牌一样在环上移动:只有紧邻标记的入环需要 2 个空槽,
环内传输完全不受限,代价几乎为零。

## 2. 机制

对象:控制 vnet(单 flit 包,`buffers_per_ctrl_vc=1`,因此 **槽 = VC**)。
每个有向环(6 个方向 × 每 vnet)初始化时在坐标 0 路由器的对向输入口标记 1 个
critical bubble。

标记注册表放在 `GarnetNetwork`(全局单一事实来源):
`m_cbs_mark[router][dirn6][vnet]`,方向索引 E,W,N,S,U,D = 0..5。

两条规则(均在 SwitchAllocator 中,判断依据是"该输出口的下游输入口是否持有标记"):

1. **入环规则**(SA-I,`send_allowed` 非自适应分支):若本次传输是**入环**
   (`inport_dirn != opposite(outport_dirn)`,即注入或换维),且下游输入口持有
   标记,则要求下游该 vnet **空闲 VC ≥ 2**,否则本轮不放行(计入
   `cbs_entry_blocks`)。效果:入环永远不会占掉被标记的最后一个空槽。
2. **环内位移规则**(SA-II,`arbitrate_outports` 完成 `decrement_credit` 之后):
   若本次传输是**环内直行**(`inport_dirn == opposite(outport_dirn)`)、下游输入口
   持有标记、且分配后下游空闲 VC 变为 0,则把标记**上移**到本包腾出的槽
   (计入 `cbs_mark_moves`)。效果:环内包可以吃掉"最后一个空槽",但 bubble
   守恒——只是换了位置。

## 3. 正确性论证

- **不变量**:每个有向环、每个 ctrl vnet 恒有 ≥1 个空槽。入环受规则 1 保护;
  环内传输"消耗下游一个槽 + 腾出上游一个槽",环上空槽总数不变,规则 2 只是
  让标记跟着那个守恒的空槽走。
- **不变量 ⇒ 无死锁**:环不满则环上至少一个包的下游有空槽,DOR 下该包必然可
  前进(单 flit 包不存在跨路由器占多槽),归纳可得环上所有包最终前进;维间
  依赖因 DOR 严格降维而无环。
- **保守性(不会过量放行)**:判断用的是本路由器 OutputUnit 的 credit 视图
  (`count_free_vcs`)。分配即时可见、释放经 credit 延迟可见,因此该视图只会
  **低估**下游空闲槽数,检查只可能偏严,不可能偏松。
- **无竞争**:同一下游输入口每周期至多接收一个包(单条链路),标记的读-改-写
  不存在同周期冲突。

## 4. 实现(最小侵入,全部由 `--enable-cbs` 门控)

| 文件 | 改动 |
|---|---|
| `GarnetNetwork.py` | `enable_cbs = Param.Bool(False, ...)` |
| `configs/network/Network.py` | `--enable-cbs` 命令行选项 |
| `GarnetNetwork.hh/.cc` | 标记注册表、`cbsInit/cbsHasMark/cbsMoveMark/cbsDownstreamRouter/cbsOppositeDirn`、统计量、init() 中的 fatal_if 约束 |
| `OutputUnit.hh/.cc` | `count_free_vcs(vnet)`(数该 vnet 空闲 VC) |
| `SwitchAllocator.hh/.cc` | `cbs_governs()` 判定 + 上述两条规则 |

约束(违反直接 `fatal`):需 `--routing-algorithm=3`(TORUS_3D_DOR);需非零
`--torus-x/y/z`;不可与 `--wormhole` 同用;**`--vcs-per-vnet ≥ 2`**(否则紧邻
标记的入环点永远凑不齐 2 个空槽,低负载下会永久阻塞)。

统计:`system.ruby.network.cbs_entry_blocks` / `cbs_mark_moves`。

## 5. 实验设置

4×4×4 Torus3D,64 CPU/dirs,4 VCs/vnet,`--inj-vnet=0`,10000 周期,
注入率 0.05–1.00 步长 0.05(包/节点/系统周期;Ruby:system = 2:1,故网络侧
最大注入 0.5 包/节点/网络周期)。三种模式 × 四种流量 × 20 个注入率 = 240 点:

- `torus3d_dor` —— 算法 3,无保护(不安全基线);
- `torus3d_dor_cbs` —— 算法 3 + CBS(本工作);
- `torus3d_adaptive_escape` —— 算法 4,自适应 + escape VC(Topic 1 基线)。

复现:`python3 run_sweep_topic2.py`;绘图 `python3 plot_results_topic2.py`。

## 6. 结果

摘要(`summary_topic2.csv`;吞吐单位:包/节点/Ruby 周期,稳定 = 注入接受率 ≥0.9):

| 流量 | 指标 | DOR 裸 | DOR+CBS | 自适应+escape |
|---|---|---|---|---|
| uniform | 低载时延 / 峰值稳定吞吐 | 11.03 / 0.499 | 11.03 / 0.499 | 11.04 / 0.499 |
| neighbor | 同上 | 7.00 / 0.499 | 7.00 / 0.499 | 7.00 / 0.499 |
| tornado | 同上 | 11.00 / 0.499 | 11.00 / 0.499 | 11.04 / 0.499(高载时延升至 13.1) |
| **transpose** | 同上 | 11.06 / **0.224**(0.5 起失稳) | 11.06 / **0.258**(0.6 起失稳) | 11.04 / 0.499(不失稳) |

要点:

1. **零开销**:uniform/neighbor/tornado 上 CBS 曲线与裸 DOR 重合(uniform 满载
   时延差 ≤0.05 周期);neighbor/tornado 全程 `cbs_entry_blocks = 0`。
2. **transpose 上反而更好**:峰值稳定吞吐 0.224 → 0.258(**+15%**),失稳点
   0.5 → 0.6;注入率 0.5 处平均时延 340 → 98 周期,接受率 0.842 → 0.972。
   机理:入环规则在环将满时优先保环内包前进,等效于饱和前的注入准入控制,
   抑制了饱和树的形成——与 bubble 流控文献报告的现象一致。
3. **机制可观测**:`cbs_entry_blocks` 在 transpose 饱和段陡增(峰值 28 万);
   `cbs_mark_moves` 在饱和拐点(0.5)达峰后回落——环持续全满时"填满最后一个
   空槽"的事件本身变少。
4. **tornado 侧写**:自适应路由在 tornado 上时延随负载升至 13.1,而 DOR/CBS
   恒为 11.0——自适应的分散代价;CBS 保留了 DOR 的最优行为。

### 死锁探针(单独长跑)

transpose@1.0、200k 周期:vcs=2 与 vcs=1 下裸 DOR 均**未**触发硬死锁(gem5
50k 周期死锁检测未报警),只是深度拥塞(vcs=1 时平均时延 7.7 万周期)。这符合
预期:死锁需要整环依赖闭合,4 节点环 + 最短路由下概率极低,但**非零**——裸
DOR 的正确性是概率性的,CBS 把它变成**构造性保证**。诚实备注:深拥塞探针中
CBS 的入环节流有 ~1.6% 的注入代价(2,382,420 对 2,420,150),属预期开销;
在 10k 周期主扫描的所有稳定工作点上无此代价。

## 7. 与 Topic 1 的关系

- **补上同一基座的正确性缺口**:队友的算法 3(TORUS_3D_DOR)是无保护的;CBS
  正是给这条路径提供死锁保护,与他的拓扑/路由代码零冲突(`--enable-cbs` 门控,
  算法 4 行为不变)。
- **两类流控的对照**:escape VC 属**通道划分**(牺牲 1/4 VC 换安全);CBS 属
  **缓冲占用不变量**(全部 4 条 VC 可用)。二者作用在同一基础设施的不同层面,
  报告可按"路由层(Topic 1)/ 流控层(Topic 2)"分层叙述。
- **评测完全可比**:沿用 Topic 1 的拓扑、流量模式、指标与脚本结构,曲线可直接
  同图比较(自适应 + escape 在 transpose 上仍最优,因为它改变的是路径本身;
  CBS 不改路径,改的是"钱怎么留")。

## 8. PCN 视角(通往第二项流控)

CBS 的不变量即"**每个循环流动性池保留一单位流动性**":标记 = 一单位不可花的
准备金,入环 = 外部资金入池需超额准备,环内传输 = 池内转账不减总流动性。这为
Topic 2 的第二项(新意方案:双侧共享信用池 + 流动性准备金)提供了同一叙事下
的出发点。
