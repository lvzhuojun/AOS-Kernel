"""
AOS-Kernel 核心状态定义
基于 7 层认知架构的状态管理
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class AOSState(BaseModel):
    """
    AI 操作系统内核状态
    
    支持 7 层认知架构：
    1. 理解 (Understanding) - intent
    2. 记忆 (Memory) - memory
    3. 计划 (Planning) - plan
    4. 权限 (Permission) - 通过权限检查模块处理
    5. 执行 (Execution) - tool_calls, execution_results
    6. 验证 (Verification) - verification_feedback
    7. 恢复 (Recovery) - retry_count
    """
    
    # 1. 理解层：用户意图
    intent: str = Field(
        default="",
        description="用户输入的原始意图或任务描述"
    )
    
    # 2. 记忆层：短期和长期记忆
    memory: Dict[str, Any] = Field(
        default_factory=dict,
        description="记忆存储，包含短期记忆（会话上下文）和长期记忆（知识库）"
    )
    
    # 3. 计划层：执行计划
    plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="执行计划，包含步骤化的任务分解"
    )
    
    # 4. 权限层：通过独立的权限检查模块处理，不直接存储在状态中
    
    # 5. 执行层：工具调用和执行结果
    tool_calls: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="工具调用记录，包含调用的工具、参数和元数据"
    )
    
    execution_results: Dict[str, Any] = Field(
        default_factory=dict,
        description="执行结果，键为工具调用ID或步骤ID，值为执行结果"
    )
    
    # 6. 验证层：验证反馈
    verification_feedback: Dict[str, Any] = Field(
        default_factory=dict,
        description="验证反馈，包含执行结果的验证状态和反馈信息"
    )
    
    # 7. 恢复层：重试计数
    retry_count: int = Field(
        default=0,
        ge=0,
        description="当前任务的重试次数，用于恢复机制"
    )
    
    # 额外字段：当前执行阶段
    current_phase: Optional[str] = Field(
        default=None,
        description="当前执行阶段：understanding, planning, execution, verification, recovery"
    )
    
    # 额外字段：错误信息
    error: Optional[str] = Field(
        default=None,
        description="错误信息，如果有的话"
    )
    
    class Config:
        """Pydantic 配置"""
        extra = "allow"  # 允许额外字段，便于扩展
        json_encoders = {
            # 可以添加自定义编码器
        }
    
    def add_tool_call(self, tool_name: str, parameters: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        添加工具调用记录
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            metadata: 可选的元数据
            
        Returns:
            工具调用ID
        """
        call_id = f"tool_call_{len(self.tool_calls)}"
        tool_call = {
            "id": call_id,
            "tool": tool_name,
            "parameters": parameters,
            "metadata": metadata or {},
            "timestamp": None  # 可以添加时间戳
        }
        self.tool_calls.append(tool_call)
        return call_id
    
    def add_execution_result(self, call_id: str, result: Any, success: bool = True):
        """
        添加执行结果
        
        Args:
            call_id: 工具调用ID
            result: 执行结果
            success: 是否成功
        """
        self.execution_results[call_id] = {
            "result": result,
            "success": success,
            "timestamp": None  # 可以添加时间戳
        }
    
    def add_verification_feedback(self, call_id: str, feedback: Dict[str, Any]):
        """
        添加验证反馈
        
        Args:
            call_id: 工具调用ID或步骤ID
            feedback: 验证反馈信息
        """
        self.verification_feedback[call_id] = feedback
    
    def increment_retry(self):
        """增加重试计数"""
        self.retry_count += 1
    
    def reset_retry(self):
        """重置重试计数"""
        self.retry_count = 0
    
    def get_memory(self, key: str, default: Any = None) -> Any:
        """
        获取记忆
        
        Args:
            key: 记忆键
            default: 默认值
            
        Returns:
            记忆值
        """
        return self.memory.get(key, default)
    
    def set_memory(self, key: str, value: Any):
        """
        设置记忆
        
        Args:
            key: 记忆键
            value: 记忆值
        """
        self.memory[key] = value
