from google import genai
import os

# 1. 配置你的 API KEY
# 如果你的 key 在环境变量里，用 os.getenv('GEMINI_API_KEY')
# 如果不在，直接把 key 填在下面引号里: "AIzaSy..."
GOOGLE_API_KEY = os.getenv('GEMINI_API_KEY') 

if not GOOGLE_API_KEY:
    print("错误: 请先设置 GOOGLE_API_KEY 环境变量或直接在代码中填入 Key")
else:
    # 使用新的 google-genai SDK (v1.0+)
    client = genai.Client(api_key=GOOGLE_API_KEY)

    print("正在查询可用模型...\n")
    try:
        # 2. 列出所有模型
        for m in client.models.list():
            # 过滤出支持 'generateContent' 的模型 (新 SDK 属性可能不同，这里打印所有或者根据 name 过滤)
            # 新 SDK 返回的对象通常有 name 属性
            if 'gemini' in m.name.lower(): 
                 print(f"- {m.name}")
    except Exception as e:
        print(f"查询失败: {e}")