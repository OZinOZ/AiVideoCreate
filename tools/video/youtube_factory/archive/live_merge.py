"""
Filename: video_perspective_warper.py
Description: 使用 OpenCV 将正面平直的视频进行透视变换（Corner Pinning），
             使其变成带有斜透视的视频，以便嵌入到挖空的背景图中。
Compliance: 严格分层, 配置前置, 独立函数, 完整日志记录, Pylint标准。
"""

import sys
import os
import cv2
import numpy as np

# ================= 配置部分 =================
CONFIG = {
    # 假设这是你用 AI 生成的纯正面视频 (比如正面燃烧的火)
    "input_video": "straight_fire.mp4",    
    # 输出的斜透视视频
    "output_video": "slanted_fire.mp4",    
    # 你的背景母图的分辨率（务必保持一致，比如 1920x1080）
    "output_size": (1920, 1080),           
    "fps": 30,                             
    
    # 【核心变量 1】：原视频的四个顶点坐标 (左上, 右上, 右下, 左下)
    # 假设你生成的正面视频是 800x600 的分辨率
    "src_points": [(0, 0), (800, 0), (800, 600), (0, 600)],
    
    # 【核心变量 2】：目标背景图上“壁炉挖空区域”的四个顶点坐标 (左上, 右上, 右下, 左下)
    # 你只需在 PS 或画图软件里，把壁炉那四个角的 X,Y 坐标量出来填在这
    "dst_points": [(500, 300), (900, 350), (880, 700), (480, 800)]
}

# ================= 功能函数 =================

def validate_configuration(config_dict):
    """校验配置参数是否完整且文件是否存在"""
    print("[STEP 1] 开始校验配置与运行环境...")
    
    if not os.path.exists(config_dict["input_video"]):
        print(f"[ERROR] 找不到输入视频文件: {config_dict['input_video']}")
        print("[INFO] 请确保正面视频已生成并放置在正确路径。")
        return False
        
    if len(config_dict["src_points"]) != 4 or len(config_dict["dst_points"]) != 4:
        print("[ERROR] 坐标点配置错误，源点和目标点必须严格提供4个顶点。")
        return False
        
    print("[SUCCESS] 配置校验通过。")
    return True

def calculate_transform_matrix(src_pts, dst_pts):
    """计算透视变换矩阵 (Perspective Matrix)"""
    print("[STEP 2] 正在计算透视变换矩阵...")
    try:
        src_array = np.float32(src_pts)
        dst_array = np.float32(dst_pts)
        matrix = cv2.getPerspectiveTransform(src_array, dst_array)
        print("[SUCCESS] 透视变换矩阵计算成功。")
        return matrix
    except Exception as e:
        print(f"[ERROR] 矩阵计算失败，坐标格式可能有误: {str(e)}")
        return None

def process_video_frames(config_dict, matrix):
    """逐帧读取视频并应用透视变换，然后写入新视频"""
    print("[STEP 3] 正在开启视频逐帧透视变换处理...")
    
    cap = cv2.VideoCapture(config_dict["input_video"])
    if not cap.isOpened():
        print(f"[ERROR] OpenCV 无法读取视频流: {config_dict['input_video']}")
        return False
        
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(
        config_dict["output_video"], 
        fourcc, 
        config_dict["fps"], 
        config_dict["output_size"]
    )
    
    if not out.isOpened():
        print(f"[ERROR] 无法初始化视频写入器: {config_dict['output_video']}")
        cap.release()
        return False

    print("[INFO] 开始逐帧渲染，请耐心等待...")
    frame_count = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break  # 视频帧已全部读取完毕
                
            # 核心处理：对当前帧应用矩阵变换，将其“拉扯”成斜透视
            # 超出目标区域的边缘部分默认填充为纯黑色 (0, 0, 0)
            warped_frame = cv2.warpPerspective(
                frame, 
                matrix, 
                config_dict["output_size"], 
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT, 
                borderValue=(0, 0, 0)  
            )
            
            out.write(warped_frame)
            frame_count += 1
            
            if frame_count % 30 == 0:
                print(f"[INFO] 已处理 {frame_count} 帧...")
                
        print(f"[SUCCESS] 视频处理完毕，总计成功渲染 {frame_count} 帧。")
        cap.release()
        out.release()
        return True
        
    except Exception as e:
        print(f"[ERROR] 渲染过程中发生致命异常: {str(e)}")
        cap.release()
        out.release()
        return False

def export_result_log(success, output_path):
    """输出最终结果日志"""
    print("[STEP 4] 汇总任务执行结果...")
    if success:
        print(f"[RESULT] 大功告成！斜透视视频已保存至: {output_path}")
        print("[HINT] 后期只需将这层视频放置在“挖空母图”底层，黑底会自动被遮挡。")
        return True
    print("[ERROR] 任务未能顺利完成，请检查上文日志。")
    return False

# ================= 主逻辑层 =================

def main():
    """主程序入口：严格执行底层函数调用，无分支处理逻辑"""
    print("=== 启动视频透视变形 (Corner Pinning) 工具 ===")
    
    # 1. 环境与配置校验
    if not validate_configuration(CONFIG):
        sys.exit(1)
        
    # 2. 核心数学计算
    trans_matrix = calculate_transform_matrix(CONFIG["src_points"], CONFIG["dst_points"])
    if trans_matrix is None:
        sys.exit(1)
        
    # 3. 视频帧重绘
    process_status = process_video_frames(CONFIG, trans_matrix)
    if not process_status:
        sys.exit(1)
        
    # 4. 落地与记录
    if not export_result_log(process_status, CONFIG["output_video"]):
        sys.exit(1)
        
    print("=== 流程全部结束 ===")

if __name__ == "__main__":
    main()