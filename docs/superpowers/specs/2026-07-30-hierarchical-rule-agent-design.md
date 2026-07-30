# Terran 分层规则智能体设计

## 背景与目标

当前 V0.1 通过 `GameSnapshot -> TacticalAdvisor -> MacroIntent -> SimpleExecutor`
跑通了 Terran 对局链路，但 `SimpleRulePolicy` 只有补人口、造兵营、训练 Marine 和阈值
进攻等少量独立规则，不能表达短期生产计划、科技前置、任务生命周期、侦察记忆或紧急
防守。

本设计参考论文
[TStarBots: Defeating the Cheating Level Builtin AI in StarCraft II in the Full Game](https://arxiv.org/pdf/1809.07193v3)
中 TStarBot2 的 DataContext、分层控制器和模块化规则思想，在现有项目中实现一套
Terran/BurnySc2 适配版分层规则智能体。实现目标是复现架构，不复现论文的
Zerg-vs-Zerg、AbyssalReef、PySC2 实验设置，也不宣称达到论文报告的胜率。

首版只提供一套完整策略：两基地 Marine/Marauder Stim 时机进攻。策略内容用于验证
各层协作，架构必须允许以后增加其他生产或战斗策略。

## 范围

首版包含：

- 可序列化状态黑板；
- ProductionStrategy 和 CombatStrategy 两个上层控制器；
- Economy、Construction、Production、Technology、Scout、Combat 六个下层 Manager；
- 高层命令、任务生命周期和统一命令调度；
- 矿物、气体、人口、建造工人和生产设施冲突处理；
- 两基地 Marine/Marauder Stim 建造与生产流程；
- 定时 SCV 侦察、基地受袭防守、集结、主力进攻和增援；
- 执行结果反馈、有限重试、任务超时和重新规划；
- 结构化决策日志与不启动 SC2 的单元测试。

首版不包含：

- RDF、OWL、知识图谱或本体推理；
- 强化学习、模仿学习或自适应参数训练；
- Zerg、Protoss 或多套 Terran 策略；
- Medivac、Siege Tank、空军、隐形检测或复杂反制；
- 精细编队、寻路、逐单位集火、拉扯等高级微操；
- 对任一内置 AI 难度的胜率承诺。

## 架构

总体数据流为：

```text
BurnySc2 observation
        |
        v
OntologySc2Bot.create_snapshot()
        |
        v
GameSnapshot
        |
        v
HierarchicalRulePolicy
        |
        +--> StrategicBlackboard
        |
        +--> ProductionStrategy ------+
        |                              |
        +--> CombatStrategy -----------+--> high-level commands
                                       |
                                       v
                    Economy / Construction / Production
                    Technology / Scout / Combat Managers
                                       |
                                       v
                              candidate MacroIntents
                                       |
                                       v
                                CommandScheduler
                                       |
                                       v
                                  MacroIntents
                                       |
                                       v
                                 SimpleExecutor
                                       |
                                       v
                              BurnySc2 unit commands
                                       |
                                       v
                              execution-result feedback
```

`HierarchicalRulePolicy` 继续实现现有接口：

```python
def recommend(self, snapshot: GameSnapshot) -> list[MacroIntent]: ...
```

新增可选反馈协议：

```python
class ExecutionAwareAdvisor(Protocol):
    def observe_execution(
        self,
        intent: MacroIntent,
        result: ExecutionResult,
    ) -> None: ...
```

`OntologySc2Bot` 在执行每个意图后，仅当 advisor 满足该协议时回传结果。这样
`SimpleRulePolicy`、`OntologyAdvisorStub` 和其他只实现 `recommend()` 的 advisor
保持兼容。

策略内部不会直接依赖 `EventLogger`。另一个可选协议
`TraceableAdvisor.drain_events() -> tuple[StrategyEvent, ...]` 暴露自上次 drain 后的
领域事件；`StrategyEvent` 只含事件类型、game loop 和标量详情。bot 在每次推荐和执行
反馈后 drain 事件，并同时交给 `EventLogger` 和 `MetricsCollector`。

## 目录与职责

新增目录：

```text
src/sc2_ontology_agent/policy/hierarchical/
├── advisor.py
├── blackboard.py
├── commands.py
├── scheduler.py
├── production_strategy.py
├── combat_strategy.py
└── managers/
    ├── economy.py
    ├── construction.py
    ├── production.py
    ├── technology.py
    ├── scout.py
    └── combat.py
```

各文件职责如下：

- `advisor.py`：确定每轮调用顺序，更新黑板，调用上层策略和下层 Manager，并把候选
  意图交给 scheduler；它不包含具体游戏规则。
- `blackboard.py`：保存战略阶段、高层命令、任务、侦察记忆、资源倾向和最近执行结果。
- `commands.py`：定义框架无关的高层命令、任务键、状态枚举和候选意图元数据。
- `scheduler.py`：做动作可用性检查、优先级排序、去重和同一步资源预留。
- `production_strategy.py`：维护短期建造队列和两基地生化策略阶段。
- `combat_strategy.py`：维护发展、集结、防守和进攻模式。
- `managers/*.py`：只读取自身需要的黑板视图，将高层目标翻译为候选 `MacroIntent`。

现有 `SimpleRulePolicy` 保留。`BotConfig` 增加 `policy`，合法值为 `simple` 和
`hierarchical`，默认值为 `hierarchical`。`runner.py` 通过唯一 advisor factory 根据
该值创建策略；这样后续实验可以显式比较简单规则与分层规则。开发和批量示例配置均
改为 `policy: hierarchical`。

## 领域状态

`StrategicBlackboard` 只保存数字、布尔值、字符串、枚举、tuple 和冻结 dataclass。
它不保存 BurnySc2 `Unit`、`Units`、tag、`Point2` 或客户端对象。

黑板包含：

- 最近一次 `GameSnapshot`；
- `ProductionPhase`：`OPENING`、`EXPANSION`、`TECH_UP`、`MUSTER`、`ATTACK`；
- `CombatMode`：`DEVELOP`、`RALLY`、`DEFEND`、`ATTACK`；
- 当前 `ResourcePriority`；
- 有序生产目标；
- 按语义键索引的任务；
- 侦察是否已计划、是否已接受及上次侦察时间；
- 防守前的战斗模式，用于威胁解除后恢复；
- 首次进攻和当前进攻波次状态；
- 最近被 scheduler 抑制的原因及执行反馈。

为支持这些决策，`GameSnapshot` 增加以下可序列化事实：

- `townhall_count`、`ready_townhall_count`、`orbital_count`；
- `refinery_count`、`ready_refinery_count`；
- `barracks_techlab_count`、`barracks_reactor_count`；
- `marauder_count`、`idle_marauder_count`、`pending_marauder_count`；
- `army_supply`；
- `mineral_saturation_deficit`、`gas_saturation_deficit`；
- `enemy_combat_units_visible`；
- `enemy_units_near_base`；
- `stim_researched`、`stim_pending`。

两个 saturation deficit 是理想采集人数减去实际采集人数的有符号合计。Executor
仍负责选择实际工人和资源点。`enemy_units_near_base` 由 bot 适配层用配置的防守半径
计算，只把计数写入快照；策略层不接触敌军位置。`army_supply` 在适配层按 Marine 1、
Marauder 2 计算。

## 高层命令与宏观意图

上层策略向黑板写入有限高层命令：

- `ProductionGoal`：期望建造、升级或单位组成；
- `ResourceDirective`：当前优先矿物或气体；
- `ScoutDirective`：侦察目标和允许窗口；
- `CombatDirective`：集结、防守、进攻或增援。

Manager 最终产生现有 `MacroIntent`。`IntentType` 增加：

```text
BUILD_REFINERY
EXPAND_COMMAND_CENTER
UPGRADE_ORBITAL
BUILD_TECHLAB
BUILD_REACTOR
RESEARCH_STIM
TRAIN_MARAUDER
SCOUT_ENEMY_START
RALLY_ARMY
DEFEND_BASE
ATTACK_ENEMY
```

原有 `ATTACK_ENEMY_START` 保留给 `SimpleRulePolicy`，分层策略使用语义更完整的
`ATTACK_ENEMY`。每个分层策略意图的 `parameters` 至少携带 `task_key` 和
`source_manager`，值仍限制为标量领域类型。

## 单一生产策略

默认配置值如下：

```yaml
bot:
  policy: hierarchical
  worker_limit: 44
  supply_buffer: 6
  max_barracks: 2
  expansion_worker_threshold: 20
  scout_start_time_seconds: 90
  attack_army_supply: 24
  reinforcement_army_supply: 8
  marine_to_marauder_ratio: 2
  defense_radius: 30
  rally_map_fraction: 0.35
  task_retry_limit: 3
  task_retry_cooldown_steps: 2
  task_timeout_seconds: 120
```

现有字段继续采用严格 YAML 校验。`rally_map_fraction` 必须是大于 0 且小于 1 的
浮点数；其余新增数量和时间字段必须为正整数，`task_retry_limit` 可为零。选择
`hierarchical` 时 `max_barracks` 至少为 2。原有 `attack_marine_threshold` 继续供
`simple` 使用，分层策略不读取该字段。

ProductionStrategy 维护以下顺序目标：

1. Supply Depot；
2. 第一座 Barracks；
3. 第一座 Refinery；
4. 第一座 Orbital Command；
5. 第二座 Command Center；
6. 第二座 Barracks；
7. 一座 Barracks Tech Lab 和一座 Barracks Reactor；
8. Stim；
9. 维持 Marine/Marauder 约 2:1 的生产比例。

SCV 在不影响更高优先级紧急任务且 Command Center 空闲时持续生产到 44。Supply
Depot 是反应式规则：预计人口余量达到 buffer 且没有同类 pending 任务时，其优先级
高于当前普通建造目标。

EconomyManager 在存在空闲工人或矿气饱和度不平衡时提交
`DISTRIBUTE_WORKERS`，并通过 intent parameter 表达资源倾向。第一座 Refinery ready
后，在 Stim 所需气体尚未储备完成时优先 gas；满足 Stim 储备后优先 minerals。
Executor 使用 BurnySc2 的 worker distribution 能力完成具体调配。

阶段转换条件：

- `OPENING -> EXPANSION`：第一座 Barracks、Refinery 和 Orbital 已完成；
- `EXPANSION -> TECH_UP`：第二基地与第二座 Barracks 已 ready；
- `TECH_UP -> MUSTER`：Tech Lab、Reactor 和 Stim 均完成；
- `MUSTER -> ATTACK`：`army_supply >= attack_army_supply`；
- `ATTACK` 保持到游戏结束，空闲增援按独立小队阈值加入。

资源不足不会跳过队首目标。科技前置缺失时，TechnologyManager 或
ConstructionManager 把缺少的前置目标插到当前目标之前。

## 战斗与侦察策略

ScoutManager 在游戏时间达到 `scout_start_time_seconds` 后提交一次
`SCOUT_ENEMY_START`。任务 accepted 后本局不重复派遣；任务 failed 且未达到重试上限
时，按冷却周期再次尝试。Executor 选择一个可用 SCV 并移动到敌方出生点，具体工人和
路径不进入领域模型。

CombatStrategy 默认处于 `DEVELOP`：

- ProductionPhase 进入 `MUSTER` 后切换为 `RALLY`；
- 部队达到进攻阈值后切换为 `ATTACK`；
- 任意阶段只要 `enemy_units_near_base > 0` 就切换为 `DEFEND`；
- 连续一次决策观察不到基地附近敌军后，退出 `DEFEND` 并恢复防守前模式。

RALLY 的目标点由 Executor 在己方主基地到敌方出生点的连线上按
`rally_map_fraction` 计算。首次主力进攻指挥全部 Marine 和 Marauder；此后只指挥空闲
增援。增援的 `army_supply` 达到 `reinforcement_army_supply` 后从集结点加入进攻。

DEFEND 选择离 ready townhall 最近的可见威胁作为目标，并指挥当前战斗单位防守。
没有可见威胁时返回 `waiting`，让下次快照重新判断。ATTACK 优先攻击可见敌方建筑，
否则攻击已知敌方出生点。

## Scheduler

每个候选意图包含：

- 意图及来源 Manager；
- 矿物、气体和人口成本；
- 是否占用建造工人；
- 所需生产设施类别；
- 是否为紧急命令；
- 对应任务键。

Scheduler 按以下顺序处理：

1. 去除已完成、已 accepted、正在 pending 或仍处冷却期的任务；
2. 去除当前科技树和快照事实不允许的动作；
3. 按紧急标记和数值优先级稳定排序；
4. 从当前矿物、气体和人口中保守预留；
5. 每轮最多选择一个需要建造工人的意图；
6. 同一 ready/idle 生产设施容量不能被重复预留；
7. 同类型、同任务键意图只保留一个；
8. 返回全部互不冲突的意图；没有动作时返回 `IDLE`。

优先级从高到低为：

1. 防守；
2. 防止 supply block；
3. 保持已有基地生产；
4. 当前建造或科技队首目标；
5. 集结和增援；
6. 侦察；
7. 扩张与非紧急科技。

紧急防守只抢占尚未调度的普通任务，不取消游戏中已经开始的建筑、单位或升级。

## 任务生命周期与反馈

任务状态为：

```text
PLANNED -> SCHEDULED -> ACCEPTED -> COMPLETED
             |             |
             +-> WAITING    +-> TIMED_OUT
             +-> REJECTED
             +-> FAILED
```

含义和处理：

- `PLANNED`：上层目标已创建；
- `SCHEDULED`：本轮 scheduler 已选中；
- `ACCEPTED`：BurnySc2 接受命令，等待快照证明完成；
- `COMPLETED`：建筑、单位、升级、pending 或阶段事实满足任务完成条件；
- `WAITING`：短暂资源、人口或设施条件不足，冷却后重试；
- `REJECTED`：宏观前置不成立，返回上层修复前置目标；
- `FAILED`：位置、工人、目标或底层命令失败，有限重试；
- `TIMED_OUT`：accepted 后超过配置秒数仍无法由快照确认完成，重新规划一次。

每个任务记录尝试次数、最后状态变化 game loop、最后原因和 accepted 时的基线计数。
构造和生产任务通过 pending/count 增长判断完成，Stim 通过升级状态判断完成，侦察通过
命令 accepted 判断完成，战斗任务由 CombatStrategy 持续状态管理而不是永久完成。

达到 `task_retry_limit` 后，普通可选任务标记失败并跳过；生产策略的必需任务重新创建
一次替代任务，使用不同建造尝试。替代任务再次耗尽重试次数时停止推进相关阶段，但
其他 Manager 继续运行，并记录 `strategy_replanned`。领域失败不抛异常。

## Executor 扩展

`SimpleExecutor` 继续负责所有 BurnySc2 对象和瞬时位置决策：

- Refinery：选择 ready townhall 附近未占用 Vespene Geyser；
- 扩张：使用 BurnySc2 `get_next_expansion()` 选择位置；
- Orbital：选择 ready、idle 的 Command Center 执行升级；
- Tech Lab/Reactor：选择无 addon、ready、idle 的 Barracks；
- Stim：选择 ready、idle 的 Barracks Tech Lab；
- Marauder：选择连接 ready Tech Lab 的 idle Barracks；
- Scout：选择一个可用 SCV 并移动到敌方出生点；
- Rally：计算领域之外的实际集结坐标；
- Defend/Attack：从实时可见单位中选择实际目标。

Executor 对资源、人口、设施空闲、科技前置、位置和目标进行二次防御式检查，并继续
返回 `accepted`、`waiting`、`rejected` 或 `failed`。策略预算不替代执行期检查。

## 日志与指标

新增事件：

```text
strategy_phase_changed
combat_mode_changed
command_proposed
command_scheduled
command_suppressed
task_state_changed
strategy_replanned
```

事件详情包括策略阶段、Manager、任务键、优先级、预算前后值、抑制原因、尝试次数和
状态转换原因。现有 `rule_trigger`、`decision`、`action_failure`、`game_end` 保留。

指标文档保持向后兼容并增加可选字段：

- `production_phase_reached`；
- `first_scout_time_seconds`；
- `first_expansion_time_seconds`；
- `stim_completed_time_seconds`；
- `first_defense_time_seconds`；
- `task_failure_count`；
- `command_suppression_count`。

## 错误处理

`waiting`、`rejected`、`failed` 和 `timed_out` 都是正常领域结果，不越过 bot 生命周期
边界抛出异常。配置错误继续在启动前失败。未知枚举、违反不变量或无法恢复的程序错误
仍由现有 bot/runner 异常链处理，并在退出前写入 `error.json` 和失败指标。

EventLogger 每条事件写后 flush。分层策略的状态只存在于单局 advisor 实例，不跨对局
复用；batch 中每局创建新 bot 和新 advisor。

## 测试设计

所有策略测试使用 `GameSnapshot`，不创建真实 SC2 客户端。

测试分层：

- Blackboard：阶段转换、任务状态、冷却、重试、超时、侦察记忆和防守模式恢复；
- ProductionStrategy：完整顺序目标和科技前置补全；
- CombatStrategy：发展、集结、防守、恢复、进攻和增援模式；
- 六个 Manager：从局部黑板状态生成正确候选意图；
- Scheduler：资源预算、气体预算、人口预算、工人互斥、设施容量、pending 去重、
  防守抢占和稳定排序；
- HierarchicalRulePolicy：从初始状态到 Stim 时机进攻的多快照场景；
- Executor：每个新增意图的 accepted/waiting/rejected/failed 行为；
- Bot snapshot：新增字段全部为可序列化领域值；
- Config：默认值、合法自定义值、边界、类型错误和未知字段；
- Logging/Metrics：新增事件和可选指标不破坏旧格式；
- Runner：默认注入 `HierarchicalRulePolicy`，每局实例隔离。

开发过程遵循测试先行：每项新行为先添加失败测试并确认失败原因，再写最小实现。

## 验收

架构复现通过以下命令验收：

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

真实对局只通过已有 opt-in 命令运行：

```bash
RUN_SC2_INTEGRATION=1 pytest -m integration -v
```

如果未实际启动 SC2 并产生结果，不报告集成成功。架构验收不以真实对局胜率为前提。
