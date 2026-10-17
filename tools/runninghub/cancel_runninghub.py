import os
import requests
import logging

# 初始化一个基础 logger，防止你的环境里没定义 logger 报错
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cancel_task(task_id: str, api_key: str = None) -> bool:
    """
    取消 RunningHub 上的任务。
    支持直接传入 api_key，如果未传入则尝试从 config 或环境变量读取。
    """
    # 1. 尝试获取 API Key (兼容你原有的 config 逻辑)
    if not api_key:
        try:
            import config
            api_key = config.KEYS.get("runninghub")
        except (ImportError, AttributeError):
            # 如果没有 config 模块，尝试从环境变量兜底获取
            api_key = os.getenv("RUNNINGHUB_API_KEY")

    if not api_key:
        logger.error("❌ Missing RunningHub API Key in config or environment variables.")
        return False

    url = "https://www.runninghub.ai/task/openapi/cancel"
    
    # 2. 构造请求头和请求体 (双保险鉴权)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"  # RunningHub V2 习惯用法
    }
    
    payload = {
        "apiKey": api_key,  # 兼容你给的旧版 Payload 写法
        "taskId": task_id
    }

    logger.info(f"🛑 正在尝试向 RunningHub 发送取消指令，任务ID: {task_id} ...")
    
    # 3. 发起请求并进行严密的异常捕获
    try:
        # 设置 timeout 防止请求卡死
        resp = requests.post(url, json=payload, headers=headers, timeout=15.0)
        
        # 即使状态码是 200，也要确保内容可以被解析为 JSON
        data = resp.json()
        
        # 兼容常见 API 的成功状态标识 (code=0, code=200, 或者 success=True)
        if data.get("code") == 0 or data.get("code") == 200 or data.get("success") is True:
            logger.info(f"✅ 成功！任务 {task_id} 已被终结。")
            return True
        else:
            logger.error(f"❌ 取消失败，服务端拒绝了请求: {data}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f"❌ 取消失败: 请求 RunningHub 接口超时 (>15s)。")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 取消失败: 网络请求异常: {e}")
        return False
    except ValueError:
        # 捕获 .json() 解析失败的异常 (通常是因为服务器挂了返回了 502/504 的 HTML 页面)
        logger.error(f"❌ 取消失败: 解析响应异常，服务端返回了非 JSON 内容: {resp.text[:100]}...")
        return False

# ==========================================
# 测试入口 (你可以直接在这里填入卡死的 Task ID 运行测试)
# ==========================================
if __name__ == "__main__":
    # 替换为你实际卡死的任务 ID，例如 "1892736189231"
    STUCK_TASK_ID = "2037065212288438274" 
    
    # 如果你的环境里配好了 config，不需要填第二个参数；如果没有，可以直接硬编码传进去
    # cancel_task(STUCK_TASK_ID, api_key="your_actual_api_key_here")
    cancel_task(STUCK_TASK_ID)