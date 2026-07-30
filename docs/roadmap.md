# 项目路线图

## V0.1：最小完整链路（已完成）

- Terran 对内置 AI 的最小完整对局；
- SCV、人口、Barracks、Marine 和阈值进攻；
- SC2Replay；
- 结构化 JSONL 日志和单局 JSON 指标；
- 独立 run ID 与顺序批量运行；
- `GameSnapshot`、`MacroIntent`、`TacticalAdvisor` 最小领域接口；
- 不启动 SC2 的单元测试与 opt-in 集成入口。

## V0.2：分层规则智能体（已实现）

- 已实现状态黑板；
- 已实现 Economy、Construction、Production、Technology、Scout、Combat Manager；
- 已实现统一命令调度器；
- 已实现资源预算、任务生命周期和失败监视；
- 已实现默认的可配置 `HierarchicalRulePolicy`，保留 `simple` 消融选项；
- 已保持现有 `GameSnapshot -> MacroIntent` 边界兼容。

V0.2 的范围是 Terran/BurnySc2 的架构适配和两基地 Marine/Marauder Stim 行为，不是论文
中 Zerg 结果的复现或胜率声明。

## V0.3：本体增强

以下工作仍待完成：

- 游戏状态到 RDF/OWL 实例的映射；
- 本体战术推荐；
- 影子模式：记录推荐但不执行；
- 有限授权模式：只允许白名单宏观意图；
- 纯规则与本体增强智能体的消融实验；
- 推荐延迟、覆盖率、冲突率和胜负等实验指标。

本体模块只替换或组合 `TacticalAdvisor`，不直接操作 `Unit`、tag 或 `Point2`。在影子
模式的数据质量、时延和可解释性验证完成前，不应进入有限授权模式。
