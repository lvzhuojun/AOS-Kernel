# AOS-Kernel

基于 7 层认知架构的 AI 操作系统内核

## 项目结构

```
AOS-Kernel/
├── core/              # 核心逻辑（状态管理、工作流编排）
├── agents/            # 不同功能的 Agent
├── sandbox/           # Docker 执行环境
├── utils/             # 工具函数和辅助模块
├── docs/              # 文档
│   ├── ARCHITECT_LOG.md    # 架构师日志
│   └── DEVELOPER_LOG.md    # 开发工程师日志
├── requirements.txt   # Python 依赖
├── .env.example       # 环境变量模板
└── README.md          # 项目说明
```

## 7 层认知架构

1. **理解 (Understanding)**: 解析用户意图
2. **记忆 (Memory)**: 短期和长期记忆管理
3. **计划 (Planning)**: 任务分解和执行计划
4. **权限 (Permission)**: 权限检查和授权
5. **执行 (Execution)**: 工具调用和代码执行
6. **验证 (Verification)**: 结果验证和反馈
7. **恢复 (Recovery)**: 错误恢复和重试机制

## 快速开始

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys
```

3. 运行项目：
```bash
# 待实现
```

## 开发规范

- 修改核心逻辑前，请在 `docs/DEVELOPER_LOG.md` 中记录你的想法
- 遇到架构问题，请在 `docs/ARCHITECT_LOG.md` 中记录"架构咨询请求"
- 遵循 7 层认知架构的设计原则

## 许可证

（待补充）
