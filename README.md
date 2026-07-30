# ontology-sc2-agent

`ontology-sc2-agent` 是一个面向 StarCraft II 完整智能体研究的实验工程。长期目标是让
本体系统根据游戏状态推荐高层战术，再由可解释的分层规则智能体执行。当前版本
**V0.2** 默认启用分层规则智能体；不包含 RDF、OWL、知识图谱或本体推理。

## V0.2 能做什么

默认的 `hierarchical` 策略在黑板上协调两层策略控制器（生产、战斗）与 Economy、
Construction、Production、Technology、Scout、Combat 六个 Manager。统一 scheduler
会预留资源、人口、建造工人和生产设施，避免同一步的冲突，并通过可选执行反馈和
可追踪事件协议维护任务重试、超时和重新规划。

其唯一完整策略是两基地 Marine/Marauder Stim 时机进攻：持续生产 SCV、补给、气矿、
扩张、Barracks addon 和 Stim；定时 SCV 侦察，受袭时防守，集结后主力进攻，并按阈值
补充增援。每场对局保存生效配置、JSONL 事件、JSON 指标；配置允许时同时保存
`SC2Replay`。单局与顺序批量实验均有独立 run ID，失败会留下诊断文件，不会覆盖已经
完成的对局。

`simple` 仍可通过 `bot.policy: simple` 选择，作为 V0.1 简化规则的消融基线；它只包含
SCV、Supply Depot、Barracks、Marine 和 Marine 阈值进攻。本项目是针对
Terran/BurnySc2 的架构适配，不是论文中 Zerg 实验结果的复现，也不承诺任何 AI 难度
上的胜率。非目标包括 RDF/OWL 推理、强化/模仿学习、多种族、多套 Terran 策略、
Medivac/Tank/空军、隐形侦测和高级逐单位微操。

## 环境要求

- Python 3.11–3.14，推荐 Python 3.11。
- `burnysc2==7.3.0`。发行包名是 `burnysc2`，Python 导入名是 `sc2`。
- Windows、macOS，或自行配置好的 Linux/Wine SC2 环境。
- 合法安装的 StarCraft II，以及独立准备的地图文件。

BurnySc2 7.3.0 声明支持 Python 3.9–3.14；本项目提高到 3.11，是为了使用稳定的现代
类型语法和工具链。本机系统 Python 可能更旧，请优先使用 `uv` 管理的隔离环境。

## 准备 StarCraft II 和地图

Windows/macOS 请通过 Battle.net 安装 StarCraft II。本项目不会下载、复制或分发游戏
和受版权保护的地图。默认配置使用 `AcropolisLE`，因为它仍是 BurnySc2 当前文档的
地图安装示例；BurnySc2 本身不附带地图。

把合法取得的地图放入：

```text
<StarCraft II 安装目录>/Maps/AcropolisLE.SC2Map
```

也可放在 `Maps` 的一层子目录中。文件名大小写必须与配置的 `map_name` 完全一致。
非默认安装位置可设置：

```bash
export SC2PATH="/path/to/StarCraft II"
```

macOS 默认安装目录是 `/Applications/StarCraft II`。Linux/Wine 的 `SC2PF`、`WINE`
和 `SC2PATH` 具体要求见 [BurnySc2 官方仓库](https://github.com/BurnySc2/python-sc2)。

## 安装

推荐使用 [uv](https://docs.astral.sh/uv/)；仓库的 `.python-version` 固定为 3.11：

```bash
uv sync
```

随后可直接使用 `.venv/bin/python`，或在允许访问 uv 缓存的普通终端中使用
`uv run`。传统 virtualenv 方式：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## 配置

`configs/dev.yaml` 是单局样例，`configs/batch.yaml` 是五局样例。所有重要策略阈值都在
YAML 中：

- `game`：地图、实时模式、`game_step` 和是否保存回放；
- `player` / `opponent`：种族和内置 AI 难度；V0.1 玩家只允许 Terran；
- `bot`：策略选择和全部策略阈值，见下表；
- `experiment`：run 名、局数、输出目录、回放目录和失败后是否继续；
- `logging`：事件开关、快照间隔与日志级别。

加载器不会忽略未知 section 或字段，也不会把 `yes/no` 静默当作布尔值；布尔值请写
`true/false`。每场开始前会把所有默认值合并后的实际配置写入该局 `config.yaml`。
`run_name` 只能包含字母、数字、点、下划线和连字符。相对输出路径以执行命令时的
当前目录为基准。`logging.log_level` 会应用到 BurnySc2 使用的 Loguru logger。

| `bot` 键 | 默认值 | 作用 |
|---|---:|---|
| `policy` | `hierarchical` | 默认分层策略；`simple` 是消融基线 |
| `worker_limit` | 44 | SCV 生产上限 |
| `attack_marine_threshold` | 10 | `simple` 的首次 Marine 进攻阈值 |
| `supply_buffer` | 6 | 补 Supply Depot 的人口余量 |
| `max_barracks` | 2 | Barracks 数量上限 |
| `decision_interval_steps` | 4 | 策略决策间隔（bot step） |
| `build_search_radius` | 20 | 执行层建造位置搜索半径 |
| `building_spacing` | 7 | 执行层建筑间距 |
| `expansion_worker_threshold` | 20 | 开始扩张所需 SCV 数 |
| `scout_start_time_seconds` | 90 | 首次 SCV 侦察时间 |
| `attack_army_supply` | 24 | 主力进攻的 army supply 阈值 |
| `reinforcement_army_supply` | 8 | 增援加入进攻的 army supply 阈值 |
| `marine_to_marauder_ratio` | 2 | 目标 Marine:Marauder 比例 |
| `defense_radius` | 30 | 快照统计基地附近敌军的半径 |
| `rally_map_fraction` | 0.35 | 主基地至敌方出生点连线上的集结比例 |
| `task_retry_limit` | 3 | 领域任务最大重试次数 |
| `task_retry_cooldown_steps` | 2 | 重试前的决策周期冷却 |
| `task_timeout_seconds` | 120 | accepted 任务确认完成的最长游戏内秒数 |

## 检查环境

```bash
python -m sc2_ontology_agent check-env
# 或安装 console script 后
sc2-agent check-env
```

可用 `--config path/to/config.yaml` 检查另一份配置。命令逐项输出操作系统、Python、
BurnySc2 版本、SC2、地图目录、目标地图、配置有效性和输出可写性，并给出缺失项的
修复方法。

## 运行单局

```bash
python -m sc2_ontology_agent run --config configs/dev.yaml
# 或
sc2-agent run --config configs/dev.yaml
```

单局返回非零退出码时，查看对应 run 目录中的 `error.json` 和 `events.jsonl`。

## 运行批量实验

```bash
python -m sc2_ontology_agent batch --config configs/batch.yaml
# 或
sc2-agent batch --config configs/batch.yaml
```

批量模式当前是顺序执行，便于 SC2 客户端清理和结果隔离。每完成或失败一局都会重写
批次汇总，因此中途退出不会丢失已经持久化的前缀结果。`continue_on_error: false`
会在首个失败后停止。

## 输出位置

默认每局输出：

```text
runs/<run_id>/
├── config.yaml
├── events.jsonl
├── metrics.json
└── error.json          # 仅失败时存在

replays/<run_id>.SC2Replay
```

批次额外写入：

```text
runs/<batch_id>/
├── config.yaml
└── batch-summary.json
```

回放由 BurnySc2 在游戏正常结束后写入；如果 SC2 启动或连接阶段失败，指标中的
`replay_path` 是计划路径，文件可能不存在。事件、指标和回放的差别及字段见
[实验数据说明](docs/experiment-data.md)。

## 测试与质量检查

这些检查不需要安装 StarCraft II：

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

真实集成测试默认跳过。只有已经安装 SC2 和 `AcropolisLE` 时才运行：

```bash
RUN_SC2_INTEGRATION=1 pytest -m integration -v
```

该命令会启动真实游戏，可能持续较长时间；只有它确实结束并生成回放后才能认为集成
测试通过。

## 常见错误

- `Python 3.9...`：不要使用 macOS 系统 Python；执行 `uv sync`。
- `SC2 installation not found`：安装游戏，或把 `SC2PATH` 指向含 `Versions` 的安装根。
- `Map 'AcropolisLE' was not found`：确认 `.SC2Map` 文件位于 `Maps` 根或一层子目录，
  且文件 stem 与 YAML 完全一致。
- `配置错误: ... unknown field`：修正拼写；加载器有意拒绝未知字段。
- 没有回放：确认 `save_replay: true`，并先看该局是否有 `error.json`；启动前失败不会
  产生有效回放。
- 批次有失败：`batch-summary.json` 的 `exceptions` 和相应 per-run `error.json`
  会保留原始异常类型与消息。

## 已知限制

- 只支持 Terran 和单一分层生产/战斗策略，未验证多地图泛化。
- Supply block 时长来自相邻观察的区间近似，不是逐 game loop 精确积分。
- 可见敌人计数采用 BurnySc2 当前观察集合，战争迷雾中的历史信息语义受上游 API 影响。
- 不设强制对局时限；极端僵局需要手动停止，已完成局的工件仍会保留。
- V0.3 前没有本体逻辑；`OntologyAdvisorStub` 默认返回空推荐且不参与正常运行。

架构边界见 [architecture.md](docs/architecture.md)，后续路线见
[roadmap.md](docs/roadmap.md)。
