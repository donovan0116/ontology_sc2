# 实验数据说明

## 三类数据各自回答什么

`SC2Replay` 是 SC2 客户端生成的视觉与游戏状态回放，适合复盘和使用官方客户端查看，
但不能可靠解释某条规则为什么触发。`events.jsonl` 是智能体内部的时间序列决策证据。
`metrics.json` 是单局聚合结果，适合表格统计。三者互补，不能互相替代。

## 每局目录

### `config.yaml`

包含该局实际生效的完整配置，包括未在输入 YAML 中出现的默认值。它是复现实验的输入
快照，不包含动态游戏状态。

### `events.jsonl`

每行是一个独立 JSON 对象，进程异常时前面的行仍可读取。公共字段：

| 字段 | 含义 |
|---|---|
| `timestamp` | UTC ISO-8601 写入时间 |
| `run_id` | 对局唯一 ID |
| `game_loop` | SC2 game loop |
| `game_time_seconds` | 游戏内秒数 |
| `event_type` | `game_start`、`snapshot`、`rule_trigger`、`decision`、`action_failure`、`first_attack`、`game_end`、`exception`，以及分层策略事件 |
| `snapshot` | 当时的可序列化 `GameSnapshot`，存在观察时写入 |
| `intent` | 类型、优先级、原因、创建 loop 和参数 |
| `execution` | `accepted/waiting/rejected/failed` 与可选原因 |
| `details` | 事件特有的标量信息 |

`event_log_enabled: false` 时不创建该文件，其他工件不受影响。

分层策略还会记录 `strategy_phase_changed`、`combat_mode_changed`、`command_proposed`、
`command_scheduled`、`command_suppressed`、`task_state_changed` 和 `strategy_replanned`。
这些事件的 `details` 包含阶段/模式、Manager、任务键、优先级、预算、抑制原因、尝试
次数或状态转换原因；它们是解释 scheduler 仲裁和执行反馈的领域证据。

### `metrics.json`

| 字段 | 定义 |
|---|---|
| `run_id` | 对局唯一 ID |
| `result` | `Victory`、`Defeat`、`Tie` 或 `Error` |
| `game_duration_seconds` | 最后观察到的游戏内时间 |
| `final_game_loop` | 最后观察到的 loop |
| `final_worker_count` / `final_marine_count` | 最终观察数量 |
| `peak_marine_count` | 所有 bot 观察中的 Marine 峰值 |
| `supply_block_duration` | 上一个观察处于 `supply_left <= 0` 时，到下一个观察的时间差之和 |
| `intent_count_by_type` | 各宏观意图被推荐的次数，包括 `IDLE` |
| `accepted_action_count` | 执行器接受的意图数 |
| `rejected_action_count` | 前置不满足的意图数 |
| `failed_action_count` | 位置、工人、目标或提交失败的意图数 |
| `waiting_action_count` | 暂时等待的意图数 |
| `first_attack_time` | 首次接受攻击命令的游戏内秒数，否则 `null` |
| `exception` | 失败类型和消息，否则 `null` |
| `replay_path` | 计划的回放路径；失败时该文件可能不存在 |
| `production_phase_reached` | 达到的最远生产阶段（分层策略可选字段） |
| `first_scout_time_seconds` / `first_expansion_time_seconds` | 首次接受侦察或扩张的游戏内秒数（可选） |
| `stim_completed_time_seconds` / `first_defense_time_seconds` | Stim 完成或首次防守的游戏内秒数（可选） |
| `task_failure_count` / `command_suppression_count` | 任务失败和 scheduler 抑制次数（可选） |

Supply block 是离散观察区间近似，误差上界受 `game_step` 和 bot 回调频率影响，不能把它
解释为逐 loop 的精确指标。`accepted` 表示命令提交给 BurnySc2，不等于建筑或单位
最终成功完成；SC2 后续拒绝需要结合事件、游戏状态和回放分析。

### `error.json`

仅边界异常时存在，包含 UTC 时间、run ID、异常类型、消息和 traceback。它用于诊断，
不代表此前的 `events.jsonl` 或 `metrics.json` 无效。

### `SC2Replay`

仅当 `save_replay: true` 且客户端运行到可保存阶段时生成。启动前缺游戏、缺地图或连接
失败不会生成有效回放。

## 批次汇总

`batch-summary.json` 包含请求局数、已完成局数、成功/失败数、胜/负/平、成功局平均游戏
时长、异常列表和每局摘要。每局结束后都会更新一次。平均时长只使用 runner 正常返回
的对局；失败局的最后观察时长仍保留在其 `metrics.json`，但不混入该平均值。
