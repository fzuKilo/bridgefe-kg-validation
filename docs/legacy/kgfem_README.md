# kgfem：知识图谱约束的大模型驱动梁桥有限元建模

论文第 4 节方法的实现。大模型是驱动者：理解输入、规划、提出每项建模决策、调用工具生成模型、诊断并修复错误；可执行桥梁知识图谱是约束者：决策前提供依据，提出时逐项校验，模型校核失败时沿溯源链定位可疑决策。

## 多智能体架构（默认）

角色与知识图谱四层一一对应，由确定性状态机 `BridgeModelingFlow` 调度（`agent/multi.py`、`agent/roles.py`）：

| 智能体 | 图谱层 | 职责 | 决策类别（= 错误类型） |
|---|---|---|---|
| InstanceAgent | 实例层 | 理解描述、写入构件与连接、声明决策清单；修正其他角色上报的实例问题 | — |
| ConstraintAgent | 约束层 | 拓扑决策（支座类型与数量、墩柱长度）；模型级 L1~L3 校核失败后的诊断与修复 | topology |
| RuleAgent | 建模规则层 | 结构体系、截面特性、约束自由度、墩柱截面、质量 | modeling_rule |
| CodeAgent | 规范层 | 材料参数、支座刚度、车道荷载、冲击系数（自行调用模态分析） | code_parameter |

- 状态机：INSTANCE → DECISION → MODEL → (REPAIR) → DONE | FAILED；任一决策智能体可 `report_instance_issue` 退回 INSTANCE，修正后图谱复核全部已接受决策（撤回不再成立者）。
- 决策按前置关系分轮推进：每轮依次调用 ConstraintAgent → RuleAgent → CodeAgent，各自只处理本类中前置已就绪的槽位。
- 阶段间 JSON 数据契约（InstanceSpec、DecisionPlan、DecisionSet、ModelIR、CheckReport）与状态转移存档于 `<题号>_contracts.json`。
- 每次角色调用使用全新上下文、只开放本层工具，减轻小模型的长上下文负担。
- 设计原则“智能体通用 + 知识路由”：提示词不含桥型逻辑，桥型知识全部在图谱中。
- 单智能体模式（`--agents single`）保留为消融对照。

## 目录与论文对应

| 模块 | 论文 | 内容 |
|---|---|---|
| `kg/knowledge.py` | 4.2（I1） | 建模规则层（MR-xx、LL-xx）、规范层（JTG D60 / JTG 3362 / JT/T 854 条文，公式为可执行表达式并带适用条件）、约束层（C-xx、L1/L2/L3）、决策模板 |
| `kg/graph.py` | 4.2 | 分层属性图（rule / code / instance / constraint / decision），可导出 JSON，接口便于换成图数据库 |
| `kg/expr.py` | 4.2 | 条文公式的安全求值器（只允许算术、比较、条件、查表与白名单函数） |
| `kg/instance.py` | 4.3 | 实例层写入与同步（跨、支承线、支座、桥墩及其连接），完整性约束 C-01~C-06，决策清单推导，公式上下文 |
| `kg/validator.py` | 4.4（I2） | 四项校验（依据存在、条件适用、数值复算、约束相容）与结构化反馈；决策层溯源边；修订后的依赖传播与事实失效 |
| `model/sections.py` | 4.4 | 截面特性积分工具（小箱梁、T 梁、现浇箱梁） |
| `model/ir.py` | 4.5 | 带溯源（prov）的中间表示 |
| `model/generator.py` | 4.5 | 由中间表示生成并运行 OpenSeesPy 脚本（自重、模态、车道荷载影响线） |
| `model/checks.py` | 4.6（I3） | L1 拓扑、L2 规范（参数按公式复算、冲击系数与基频一致）、L3 力学（反力平衡、工程量、基频范围），并定位可疑决策 |
| `agent/roles.py`、`agent/multi.py` | 4.1 | 四个图谱层角色与状态机编排、数据契约 |
| `agent/backends.py`、`agent/tools.py` | 4.7 | Claude / Ollama 通用工具循环；工具定义与各角色工具子集 |
| `agent/session.py` | 4.1 | 把图谱与模型封装为工具，执行流程关卡（实例补全 ≤ 5 轮、修复 ≤ 5 轮）并记录每轮约束违反 |
| `agent/claude.py` | 4.1 / 4.7 | Claude 驱动层：系统提示词、13 个工具、人工控制的工具调用循环；默认 `claude-opus-5`，可换基座（H2） |
| `agent/local.py` | H2 | 本地开源模型驱动层（Ollama `/api/chat`），与 Claude 共用提示词和工具；默认 `qwen3.5:9b`，较早的工具结果自动截短以控制上下文 |
| `agent/scripted.py` | — | 脚本化代理：不调用大模型，用同一套工具跑通闭环，并支持决策级 / 模型级错误注入（H3） |
| `evaluate.py` | 3.5 | 按 BridgeFE-Bench 评估决策层与响应层 |
| `cli.py` | — | 命令行入口 |

## 工具（大模型可调用）

`get_input_schema`、`write_instance`、`query_component`、`query_knowledge`、`retrieve_clause`、`execute_formula`、`compute_section_properties`、`declare_decisions`、`propose_decision`、`decision_status`、`run_modal_analysis`、`generate_model`、`finish`。

每项决策以（槽位, 取值, 单位, 依据节点）提出，例如：

```json
{"slot": "support.2.Kv", "value": 7175050.2, "unit": "kN/m",
 "evidence": ["JTG3362-8.7-Kv", "INPUT:supports[2].bearing.Ge_MPa"]}
```

不通过时返回违反的检查项、约束编号、适用条件与公式结果，例如“按 JTGD60-4.3.1-Pk 计算得 330.0，所提为 379.5”。

## 运行

脚本化代理（无需 API）：

```bash
.venv/bin/python -m kgfem.cli run --backend scripted --all
```

注入决策级错误（首次提案出错，检验反馈—修订回路）：

```bash
.venv/bin/python -m kgfem.cli run --backend scripted --all --faults "lane.Pk.{j}=scale" "support.{k}.Kv=wrong_clause" "girder.gamma=wrong_unit"
```

注入模型级错误（绕过校验篡改已接受决策，检验三级校核与定位）：

```bash
.venv/bin/python -m kgfem.cli run --backend scripted --problems C02 --model-faults girder.w=1.1
```

模拟后端自检（多智能体，无需模型；`--mock-instance-fault` 检验实例问题回路）：

```bash
.venv/bin/python -m kgfem.cli run --backend mock --all
```

Claude 驱动（需要 `ANTHROPIC_API_KEY` 或 `ant auth login`，会产生 API 费用）：

```bash
.venv/bin/python -m kgfem.cli run --backend claude --model claude-opus-5 --problems A01 --repeat 10
```

本地开源模型（需先安装 Ollama 并拉取模型，免费、离线）：

```bash
.venv/bin/python -m kgfem.cli run --backend ollama --model qwen3.5:9b --problems A01
```

每次运行在 `runs/<题号>/` 下输出：会话记录（决策、事实、日志、指标）、知识图谱 JSON、中间表示、生成的 OpenSeesPy 脚本；`runs/summary.json` 汇总评估结果。

## 已验证

- 脚本化代理在 BridgeFE-Bench 全部 33 题上决策层与响应层均与独立参考答案一致（准确率 1.000）。
- 决策级错误（数值偏差、引错条文、单位错误）均在首次提案时被拦下，按反馈修订后通过。
- 模型级错误（篡改 Pk、惯性矩、支座刚度、自重、横向折减系数、形状系数）均被 L2/L3 校核发现并定位到被篡改的决策，1 轮修复后通过。
- 多智能体编排已用模拟后端验证：33 题全部正确；实例问题上报—修正—复核回路、诊断修复回路均走通。
- 本地 qwen3.5:9b 单智能体在 A01 上 3 次运行 2 次正确（不同代码版本，见 `runs/`）；多智能体版本尚未用真实模型运行。

## 局限

- 规范条文号与数值须由专家核对；知识图谱覆盖范围限于本基准需要的建模与荷载生成条文。
- 实例层由大模型从描述中写入，图谱只能检查其完整性与合理性；若大模型把描述读错，数值复算会以错误输入为准，需靠 L3 力学校核兜底。
- 基线方案（直接生成、提示词知识、检索增强）尚未实现；它们可复用同一工具集，仅去掉 `propose_decision` 的校验与反馈。
