"""
Gemini API 连通性测试：验证 GOOGLE_API_KEY 与模型列表。

用法（在项目根目录执行）：
  python -m tests.test_gemini
  或
  python tests/test_gemini.py
"""
import os
import sys

# 从 tests/ 运行时将项目根加入 path，便于同目录其他脚本引用
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))
from google import genai

api_key = os.getenv("GOOGLE_API_KEY")
print(f"🔍 正在检查 Key: {api_key[:10]}******")

try:
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1"})
    print("展开模型列表...")
    models = client.models.list()
    available_models = [m.name for m in models]
    print(f"✅ 你的 Key 可以访问以下模型: {available_models}")
    test_model = "gemini-2.0-flash" if "gemini-2.0-flash" in available_models else available_models[0]
    print(f"🚀 尝试使用模型 {test_model} 进行测试...")
    response = client.models.generate_content(model=test_model, contents="Hello, are you there?")
    print("🔥 成功！响应内容：")
    print(response.text)
except Exception as e:
    print(f"❌ 依然失败：{str(e)}")
    print("\n💡 架构师建议：")
    print("1. 请去 Google AI Studio 检查该 Key 是否已启用 'Generative Language API'。")
    print("2. 检查你的网络环境（是否需要代理）。")
    print("3. 确认你的 API Key 是否完整（通常以 AIza 开头，长度约 39 位）。")
