# 开发工程师日志 (Developer Log)

> 本文档用于记录开发进度、技术决策和 Bug 状态。

---

## 2026-02-06 - 项目初始化

### 任务清单
- [x] 创建项目文档结构
- [x] 创建环境配置文件
- [x] 定义核心数据结构
- [x] 建立项目文件夹结构

### 技术决策

#### 1. 状态管理设计
**决策时间**: 2026-02-06

**问题**: 如何设计 AOSState 以支持 7 层认知架构？

**方案**: 
- 使用 Pydantic BaseModel 而非 TypedDict，原因：
  - 提供运行时类型验证
  - 支持序列化/反序列化
  - 更好的 IDE 支持
  - 便于与 LangChain/LangGraph 集成

**状态字段设计**:
- `intent`: 用户意图（字符串）
- `plan`: 执行计划（列表/字典结构）
- `memory`: 记忆存储（字典，支持短期和长期记忆）
- `tool_calls`: 工具调用记录（列表）
- `execution_results`: 执行结果（字典）
- `verification_feedback`: 验证反馈（字典）
- `retry_count`: 重试计数（整数）

**待确认**: 是否需要添加 `permissions` 字段用于权限层？还是权限检查作为独立模块？

#### 2. 项目结构设计
**决策时间**: 2026-02-06

**文件夹职责**:
- `core/`: 核心逻辑（状态管理、工作流编排）
- `agents/`: 不同功能的 Agent（理解、计划、执行等）
- `sandbox/`: Docker 执行环境封装
- `utils/`: 工具函数和辅助模块

### Bug 追踪

（Bug 将在此处记录）

### 待解决问题

1. **权限层设计**: 权限检查的具体实现方式？是否需要独立的权限管理模块？
2. **记忆层设计**: 短期记忆和长期记忆的存储机制？是否需要向量数据库？
3. **恢复机制**: 错误恢复的具体策略？如何定义恢复点？

---

## 开发进度

### 2026-02-07 — Phase 1 最终修复版封版
**2026-02-07: Phase 1 最终修复版封版。彻底解决了硬编码幻觉，实现了全链路物理验证与交互式 Shell。**

- 硬编码清除：移除所有业务逻辑中的 test.py/ghost.txt 等写死路径；执行层从 step description/parameters 动态提取文件名，解析失败时由 LLM(cheap) 生成代码。
- 原子化计划：Planning 层强制「创建并运行」拆分为两步（file_writer → python_interpreter）；System Prompt 禁止示例使用具体文件名，必须严格提取用户提供的文件名。
- 验证层针对性：VerificationAgent 从 step 中提取 expected_file，验证与反馈均针对计划中指定的文件名，不做泛泛检查。
- 交互模式：main.py 支持 -i/--interactive，循环接受用户指令，输入 exit 退出；清理环境脚本 scripts/clean_env.py 清空 memory.json 与 sandbox_workspace/。
- 429 与兜底：API 429 时重试 [5,10,20]s 后进入兜底；兜底从 user_prompt 还原真实用户输入，严禁返回 test.py；意图解析对「创建/运行+文件名」类指令提升置信度，避免误入澄清。

### 2026-02-06 — Phase 1 核心内核开发圆满完成
**2026-02-06: Phase 1 核心内核开发圆满完成。项目结构已规范化，通过全链路压力测试。**

- 目录规范：`tests/` 成立，`test_gemini.py` 与 `debug_stress_test.py` 迁入，导入路径已修正（从项目根执行 `python -m tests.*`）。
- 依赖与环境：requirements.txt 含 google-genai、python-dotenv、pydantic、docker；sandbox_workspace 临时文件已清理。
- 文档：README 补充 Project Structure、Features、Usage；.gitignore 覆盖 .env、memory.json、*.log、__pycache__/、sandbox_workspace/。

### 2026-02-06 — AOS-Kernel v1.0 稳定版发布
**2026-02-06: AOS-Kernel v1.0 稳定版发布。全链路闭环、语义缓存与成本控制功能全部达成。**

- 全链路闭环：理解 → 计划 → 权限 → 执行 → 验证 → 恢复（REPLAN/ABORT）完整打通；Docker 沙箱隔离、策略驱动权限网关、自愈循环（如 Case 4 ghost.txt → fixed.txt 补偿）均已实现。
- 语义缓存：MemoryManager.find_similar_lesson(intent) + successful_plans 持久化；PlanningAgent 优先命中缓存（planning_from_cache），0-Token 计划复用。
- 成本控制：LLMClient tier 路由（cheap/smart/ultra）、各 Agent 固定 tier、程序退出时打印成本统计（Cheap/Smart/缓存命中）。
- 标准化与文档：README 完善（7 层架构图、核心特性、快速开始）；main 与 llm_client 统一使用 logging 分级输出；docs/FINAL_DEMO_LOG.txt 用于保存 `python main.py --yes` 的完整演示输出。

### 2026-02-06
- ✅ 完成项目骨架初始化
- ✅ 创建核心状态数据结构
- ✅ 建立文档和日志系统

**2026-02-06: 全链路闭环集成成功，实现首个沙箱内代码自动化执行。**
- main.py 串联：理解 → 计划 → 权限 → 执行；权限网关拦截 RISKY/DANGEROUS 步骤，终端交互式审批（y/n）后继续执行。
- Docker 沙箱：常驻容器、资源限制（512m / 0.5 CPU）、单次执行 30 秒超时；程序退出时自动 stop() 销毁容器。
- 测试用例 3：在工作区创建 test.py 打印 Hello AOS-Kernel 并运行，两步均经审批后在沙箱内完成。

**内核已适配 Windows PowerShell 环境，支持 --yes 自动化测试模式。**
- 统一使用 `python` 命令（不再使用 `py`）；避免使用 `echo y | python` 等管道方式（PowerShell 支持不佳）。
- 新增 `python main.py --yes`：自动批准所有权限拦截，无需人工 input，便于在 Windows/Conda/PowerShell 下做自动化集成测试。
- DockerManager 已确认：`containers.run` 中已设置 `mem_limit="512m"`、`nano_cpus=500000000`。

**内核已具备 Layer 6/7 自愈能力，支持基于 LLM 反思的自动重规划。**
- Layer 6 VerificationAgent：对比 execution_results 与 plan.expected_outcome，简单验证（exit_code）与可选语义验证（LLM），写入 verification_feedback（SUCCESS/FAILED）。
- Layer 7 RecoveryAgent：验证失败时调用 LLM 分析错误与结果，生成策略 RETRY/REPLAN/ABORT；REPLAN 时追加 new_steps 到 state.plan 并增加 retry_count，max_retries=3 防止无限重试。
- main.py 自愈循环：执行 -> 验证 -> 若存在失败则恢复 -> REPLAN 时回到执行环节。
- Test Case 4（压力测试）：读取不存在的 ghost.txt 失败 -> 验证失败 -> 恢复层 REPLAN 追加“创建 fixed.txt” -> 再次执行后补偿成功。

**架构师审计修复（API 404 + 路径安全 + Test Case 4 意图）：**
- utils/llm_client.py：确认使用 genai.Client(api_key=...)；模型 404 时依次尝试 gemini-1.5-flash、gemini-2.0-flash、gemini-1.5-pro；新增 _smoke_test()，可 `python -m utils.llm_client` 验证 generate_content 能通。
- core/permission_gateway.py：在 verify_step 中增加路径安全校验；从 description/tool 及 step 的 path/file_path 提取路径，调用 _path_in_workspace(path)；任何访问 sandbox_workspace 之外的操作标记为 DANGEROUS。
- main.py：Test Case 4 显式使用 user_input=input_4，并注释说明 state 由 input_4 重新生成、不复用 state_3。
- 上述修复已完成，可进入 Layer 2 (Memory)，开始编写 core/memory_manager.py。

---

## 初步实现思路

### 整体架构设计

#### 1. 工作流编排（基于 LangGraph）
**思路**: 使用 LangGraph 构建状态机，将 7 层认知架构映射为工作流节点：

```
用户输入 → 理解层 → 记忆层 → 计划层 → 权限层 → 执行层 → 验证层 → [成功] 或 [失败 → 恢复层]
```

**实现要点**:
- 每个层对应一个 LangGraph 节点
- 状态在节点间传递（AOSState）
- 支持条件分支（验证成功/失败）
- 恢复层可以回退到计划层或执行层

#### 2. Agent 设计模式
**思路**: 每个认知层对应一个独立的 Agent 类：

- `UnderstandingAgent`: 使用 LLM 解析用户意图，提取关键信息
- `MemoryAgent`: 管理记忆的存储和检索（可能需要向量数据库）
- `PlanningAgent`: 将意图分解为可执行的步骤计划
- `PermissionAgent`: 检查每个步骤的权限（文件访问、网络访问等）
- `ExecutionAgent`: 在沙箱中执行工具调用或代码
- `VerificationAgent`: 验证执行结果是否符合预期
- `RecoveryAgent`: 处理错误，决定重试策略或回退方案

#### 3. 沙箱执行环境
**思路**: 使用 Docker 容器隔离代码执行：

- `DockerSandbox`: 管理 Docker 容器的生命周期
- 资源限制：CPU、内存、执行时间
- 文件系统隔离：只允许访问指定工作空间
- 网络隔离：默认无网络访问，需要时配置白名单

#### 4. 状态持久化
**思路**: 
- 短期状态：内存中（当前会话）
- 长期记忆：考虑使用向量数据库（ChromaDB/Faiss）存储知识
- 执行历史：可以序列化为 JSON 存储

#### 5. 下一步开发计划

**阶段 1: 核心工作流** (优先级：高)
1. 实现 LangGraph 工作流骨架
2. 实现 UnderstandingAgent（基础版本）
3. 实现 PlanningAgent（基础版本）
4. 实现 ExecutionAgent（基础版本，先不使用沙箱）

**阶段 2: 安全与验证** (优先级：高)
1. 实现 DockerSandbox
2. 实现 PermissionAgent
3. 实现 VerificationAgent

**阶段 3: 记忆与恢复** (优先级：中)
1. 实现 MemoryAgent（向量数据库集成）
2. 实现 RecoveryAgent
3. 状态持久化机制

**阶段 4: 优化与扩展** (优先级：低)
1. 性能优化
2. 错误处理完善
3. 监控和日志系统
4. API 服务封装

### 技术选型说明

1. **LangGraph**: 
   - 优势：状态机管理、可视化、与 LangChain 生态集成
   - 适用：工作流编排

2. **Pydantic**: 
   - 优势：类型安全、数据验证、序列化
   - 适用：状态定义、配置管理

3. **Docker**: 
   - 优势：隔离性、可移植性、资源控制
   - 适用：代码执行沙箱

4. **python-dotenv**: 
   - 优势：环境变量管理
   - 适用：配置管理

---

## Intent Parser 与 LLM 客户端设计（2026-02-06）

### 1. LLM 调用抽象（utils/llm_client.py）

**设计目标**:
- 统一封装对 Gemini / Claude 的调用入口
- 从 `.env` 中读取 `GOOGLE_API_KEY` 与 `ANTHROPIC_API_KEY`
- 通过配置方便切换 provider（`gemini` / `claude`），并预留模型名、温度等参数
- 在无 Key 或本地开发环境下，提供安全的降级行为（简单规则解析），避免直接崩溃

**核心接口**:
- `LLMClient.from_env(provider: Optional[str] = None, model: Optional[str] = None) -> LLMClient`
- `LLMClient.generate(system_prompt: str, user_prompt: str, **kwargs) -> str`

**后端策略（优先级）**:
1. 默认 provider：`gemini`，默认模型：`gemini-1.5-pro`
2. 当环境变量中设置 `LLM_PROVIDER=claude` 时，切换到 Claude
3. 当对应 Key 不存在或后端不可用时，回退到本地简单规则解析 `_local_fallback`（用于开发与测试）

### 2. Intent Parser 设计（agents/intent_parser.py）

**职责**:
- 将用户自然语言输入解析为结构化的 `AOSState`
- 实现架构师定义的“需求澄清”机制（低置信度时主动提问）

**Prompt 结构**:
- System Prompt（简要要点）:
  - 你是 AOS-Kernel 的“意图解析模块”
  - 需要从用户输入中提取：`intent`、`constraints`、`suggested_tools`、`confidence`、`clarification_questions`
  - 必须严格输出 JSON，不能包含多余说明文字
  - `constraints`：用户显式提到的限制（如“用 Python”、“不要联网”、“只能读文件不能写”等）
  - `suggested_tools`：模型认为可以使用的工具名称（如：`["file_reader", "log_analyzer"]`）
  - `confidence`：0.0 - 1.0 的浮点数，表示对意图识别的信心
  - `clarification_questions`：当信息不足时，给出 1-3 条澄清问题

- User Prompt（示例结构）:
  - 包含原始用户输入，例如：
  - `用户输入: "<<USER_INPUT>>"` 
  - 要求 LLM 按上述字段输出 JSON

**预期输出 JSON 示例**:
```json
{
  "intent": "分析 D 盘 logs 文件夹，找出报错最多的行",
  "constraints": ["仅访问 D:/logs 目录", "只读文件，不修改内容"],
  "suggested_tools": ["file_system_reader", "log_frequency_analyzer"],
  "confidence": 0.86,
  "clarification_questions": []
}
```

### 3. 与 AOSState 的映射规则

- `AOSState.intent`:
  - 直接使用 LLM 输出的 `intent` 字段；若缺失则退化为原始 `user_input`

- `AOSState.memory` 中的约定键:
  - `constraints`: LLM 输出的 `constraints` 列表
  - `suggested_tools`: LLM 输出的 `suggested_tools` 列表
  - `intent_confidence`: LLM 输出的 `confidence` 数值
  - `clarification_questions`: LLM 输出的 `clarification_questions` 列表

- `AOSState.current_phase`:
  - 当 `confidence >= 0.7` 时：设为 `"understanding"`（理解完成，可进入下一层）
  - 当 `confidence < 0.7` 时：设为 `"awaiting_clarification"`（等待需求澄清）

- `AOSState.error`:
  - 当 `confidence < 0.7` 时：
    - 若存在 `clarification_questions`：将问题合并为一段提示文案，存入 `error`
    - 若不存在：使用通用文案，例如：
      - `"当前意图置信度较低，请用更具体的语言描述你的需求。"`

### 4. 需求澄清机制（带上下文的重试入口）

- 当 `current_phase == "awaiting_clarification"` 时：
  - 上层交互模块应将 `error` + `clarification_questions` 返回给用户
  - 用户补充的说明将回流到 Intent Parser，形成新一轮解析
  - 后续 RecoveryAgent 可以利用 `intent_confidence` 与重试次数 `retry_count` 决定是否继续澄清或终止会话

---

## Planning Agent 与复杂任务拆解（2026-02-06）

### 1. LLM 客户端真实调用实现

**实现要点**:
- 使用 `google-generativeai` SDK，通过 `genai.configure(api_key=...)` 配置
- 超时机制：使用 `ThreadPoolExecutor` + `future.result(timeout=...)` 实现应用层超时（默认 60 秒）
- 重试机制：指数退避（1s, 2s, 4s），最多重试 3 次
- 降级策略：当 API Key 缺失或所有重试失败时，回退到 `_local_fallback`，确保开发流程不中断

**环境变量支持**:
- `LLM_TIMEOUT_SECONDS`: 单次请求超时（默认 60）
- `LLM_MAX_RETRIES`: 最大重试次数（默认 3）

### 2. Planning Agent 设计（agents/planning_agent.py）

**职责**:
- 接收 `AOSState`（包含 `intent` 和 `memory` 中的 `constraints` / `suggested_tools`）
- 生成原子化的执行步骤序列，赋值给 `state.plan`
- 更新 `state.current_phase = "planning"`

**计划步骤结构**:
每个步骤（Step）必须包含：
- `step_id`: 整数序号（从 1 开始）
- `description`: 这一步要做什么（简洁明确）
- `tool`: 预估要使用的工具名称（如 "file_system_reader", "log_frequency_analyzer"）
- `expected_outcome`: 这一步完成后的预期状态或输出（用于后续验证）

### 3. 复杂任务拆解的 Prompt 优化心得

#### 3.1 角色定位的重要性
**发现**: 明确告诉 LLM 它是“严谨的系统架构师”比泛泛的“助手”更有效。
- 架构师角色会自然考虑逻辑自洽、安全性和可维护性
- 这减少了后续需要显式约束的数量

#### 3.2 原子性原则的强化
**问题**: 初期 Prompt 中只提到“原子性”，但 LLM 仍可能生成复合步骤（如“读取并分析文件”）。

**优化**:
- 在 Prompt 中明确强调：“每个步骤只做一件事，避免复合操作”
- 在示例中展示清晰的原子步骤边界
- 在 `_call_llm` 的 user_prompt 中再次提醒：“确保每个步骤都是原子性的单一动作”

**效果**: 生成的步骤更细粒度，便于后续权限检查和验证。

#### 3.3 可验证性的前置考虑
**设计**: 要求每个步骤包含 `expected_outcome`，而非事后补充。

**原因**:
- 在计划阶段就思考“如何验证这一步成功”，有助于发现逻辑漏洞
- `expected_outcome` 为后续 VerificationAgent 提供了明确的验证标准
- 这形成了“计划-执行-验证”的闭环

#### 3.4 安全性意识的嵌入
**策略**: 在 Prompt 中要求“考虑每个步骤可能涉及的安全风险”。

**效果**:
- LLM 会主动识别文件访问、网络请求、系统命令等敏感操作
- 这些信息可以传递给后续的 PermissionAgent，实现“策略驱动的分级控制”

#### 3.5 约束条件的传递
**实现**: 将 `constraints` 和 `suggested_tools` 显式传递给 PlanningAgent。

**价值**:
- `constraints` 帮助 LLM 生成符合用户限制的计划（如“只能读 D 盘”）
- `suggested_tools` 提供工具选择的起点，但允许 LLM 根据实际情况调整

#### 3.6 JSON 格式的严格性
**问题**: LLM 有时会在 JSON 前后添加解释性文字。

**处理**:
- System Prompt 中明确要求：“严格输出一个 JSON 数组，不要输出任何解释性文字或多余内容”
- 在 `_call_llm` 中使用 `json.loads` 解析，失败时回退到 `_fallback_plan`
- `_fallback_plan` 基于关键词（如 "logs"）生成简单但可用的计划，确保流程不中断

#### 3.7 回退策略的设计
**设计**: `_fallback_plan` 不是简单的空计划，而是基于意图关键词的启发式计划。

**好处**:
- 即使 LLM 调用失败，系统仍能生成基本可用的计划
- 对于常见任务（如日志分析），回退计划足够具体，可以继续执行流程
- 这提高了系统的鲁棒性

### 4. 与 AOSState 的集成

- `state.plan`: 存储步骤列表（`List[Dict[str, Any]]`）
- `state.current_phase`: 计划完成后设为 `"planning"`
- `state.memory`: 保留 `constraints` / `suggested_tools` 等上下文，供后续层使用

### 5. 工作流串联

**流程**:
```
用户输入 
  -> IntentParser.parse() 
  -> 检查 confidence >= 0.7?
    -> 是: PlanningAgent.plan(state)
    -> 否: 停留在 "awaiting_clarification"，不进入计划层
```

**测试用例**:
- "帮我分析 D 盘下的 logs 文件夹，找出报错最多的行。"
  - 预期：高置信度 -> 生成 3-4 个原子步骤（列出目录、读取文件、统计报错、排序输出）
- "写一个脚本。"
  - 预期：低置信度 -> 不进入计划层，等待澄清

---

### 架构咨询请求

**问题 1**: 权限层的粒度如何定义？
- 是否需要细粒度的权限控制（如：读取文件A、写入文件B）？
- 还是粗粒度的权限控制（如：文件系统访问、网络访问）？

**问题 2**: 记忆层的存储策略？
- 短期记忆：会话内存储（内存）？
- 长期记忆：是否需要向量数据库？还是简单的键值存储？
- 记忆的检索策略：语义搜索还是精确匹配？

**问题 3**: 恢复机制的回退策略？
- 失败后回退到哪个层？（计划层？执行层？）
- 重试次数上限？
- 是否需要保存检查点（checkpoint）？
