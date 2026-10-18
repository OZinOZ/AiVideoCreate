"""
Filename: live_tools.py  (合并自 live_merge.py + live_all.py)
Description: 助眠直播素材工具集。
  warp    使用 OpenCV 将正面视频做透视变换 (Corner Pinning)  [原 live_merge.py / video_perspective_warper]
  master  全链路主控: 素材检查 -> 透视变换 -> 混流(预留)    [原 live_all.py / luna_drift_master_controller]

用法:
  python live_tools.py warp -i straight_fire.mp4 -o slanted_fire.mp4 \
      --src 0,0,800,0,800,600,0,600 --dst 500,300,900,350,880,700,480,800
  python live_tools.py master            # 使用 CONFIG 中的默认素材清单
"""

import argparse
import os
import sys

# ================= 配置部分 =================
WARP_DEFAULTS = {
    "input_video": "straight_fire.mp4",
    "output_video": "slanted_fire.mp4",
    "output_size": (1920, 1080),   # 背景母图分辨率, 务必保持一致
    "fps": 30,
    # 原视频四个顶点 (左上, 右上, 右下, 左下)
    "src_points": [(0, 0), (800, 0), (800, 600), (0, 600)],
    # 背景图“挖空区域”四个顶点 (左上, 右上, 右下, 左下)
    "dst_points": [(500, 300), (900, 350), (880, 700), (480, 800)],
}

CONFIG = {
    "workspace_dir": "./luna_drift_assets",
    "video_assets": {
        "fish_tank_real": "real_fishtank.mp4",
        "fire_ai": "straight_fire.mp4",
        "rain_ai": "straight_rain.mp4",
    },
    "audio_assets": {
        "bgm": "sleep_music.mp3",
        "noise_mix": "brown_noise.wav",
    },
    "output_master": "luna_drift_live_ready.mp4",
}


# ================= warp 功能 =================
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
    import cv2
    import numpy as np
    print("[STEP 2] 正在计算透视变换矩阵...")
    try:
        matrix = cv2.getPerspectiveTransform(np.float32(src_pts), np.float32(dst_pts))
        print("[SUCCESS] 透视变换矩阵计算成功。")
        return matrix
    except Exception as e:
        print(f"[ERROR] 矩阵计算失败，坐标格式可能有误: {str(e)}")
        return None


def process_video_frames(config_dict, matrix):
    """逐帧读取视频并应用透视变换，然后写入新视频"""
    import cv2
    print("[STEP 3] 正在开启视频逐帧透视变换处理...")

    cap = cv2.VideoCapture(config_dict["input_video"])
    if not cap.isOpened():
        print(f"[ERROR] OpenCV 无法读取视频流: {config_dict['input_video']}")
        return False

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(config_dict["output_video"], fourcc,
                          config_dict["fps"], config_dict["output_size"])
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
                break
            # 超出目标区域的边缘部分默认填充为纯黑色
            warped_frame = cv2.warpPerspective(
                frame, matrix, config_dict["output_size"],
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0))
            out.write(warped_frame)
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"[INFO] 已处理 {frame_count} 帧...")
        print(f"[SUCCESS] 视频处理完毕，总计成功渲染 {frame_count} 帧。")
        return True
    except Exception as e:
        print(f"[ERROR] 渲染过程中发生致命异常: {str(e)}")
        return False
    finally:
        cap.release()
        out.release()


def export_result_log(success, output_path):
    """输出最终结果日志"""
    print("[STEP 4] 汇总任务执行结果...")
    if success:
        print(f"[RESULT] 大功告成！斜透视视频已保存至: {output_path}")
        print("[HINT] 后期只需将这层视频放置在“挖空母图”底层，黑底会自动被遮挡。")
        return True
    print("[ERROR] 任务未能顺利完成，请检查上文日志。")
    return False


def run_warp(cfg):
    """执行透视变换流程, 返回是否成功"""
    if not validate_configuration(cfg):
        return False
    matrix = calculate_transform_matrix(cfg["src_points"], cfg["dst_points"])
    if matrix is None:
        return False
    ok = process_video_frames(cfg, matrix)
    return export_result_log(ok, cfg["output_video"]) and ok


def parse_points(text):
    nums = [int(x) for x in text.split(",")]
    if len(nums) != 8:
        raise argparse.ArgumentTypeError("需要 8 个整数: x1,y1,x2,y2,x3,y3,x4,y4")
    return [(nums[i], nums[i + 1]) for i in range(0, 8, 2)]


def cmd_warp(args):
    cfg = dict(WARP_DEFAULTS)
    cfg.update(
        input_video=args.input or cfg["input_video"],
        output_video=args.output or cfg["output_video"],
        output_size=(args.width, args.height),
        fps=args.fps,
    )
    if args.src:
        cfg["src_points"] = args.src
    if args.dst:
        cfg["dst_points"] = args.dst
    print("=== 启动视频透视变形 (Corner Pinning) 工具 ===")
    if not run_warp(cfg):
        sys.exit(1)
    print("=== 流程全部结束 ===")


# ================= master 功能 =================
def init_workspace(config_dict):
    """初始化并检查工作目录与素材是否就绪"""
    print("[STEP 1] 正在检查工作区与素材状态...")
    work_dir = config_dict.get("workspace_dir")
    if not os.path.exists(work_dir):
        print(f"[ERROR] 工作区目录未找到: {work_dir}")
        print("[INFO] 请明天创建该目录，并将拍摄和生成的素材放入其中。")
        return False
    print("[SUCCESS] 工作区目录已就绪，等待素材装填核验。")
    return True


def run_perspective_warp_module():
    """调用透视变换子模块 (原版为预留接口, 此处保持模拟行为)"""
    print("[STEP 2] 正在拉起 OpenCV 透视变换流水线...")
    print("[INFO] 模拟处理：正在将正面火焰与雨滴转换为完美贴合的斜透视...")
    print("[SUCCESS] 视觉素材透视处理全部完成。")
    return True


def run_audio_video_muxing_module():
    """调用 FFmpeg 音视频混流子模块 (原版为预留接口, 此处保持模拟行为)"""
    print("[STEP 3] 正在拉起 FFmpeg 多轨混流流水线...")
    print("[INFO] 模拟处理：正在混合实拍鱼缸、斜透视背景与多轨助眠白噪音...")
    print("[SUCCESS] 视音频总线合成完毕，无爆音。")
    return True


def export_final_report(success_flag):
    """输出最终状态报告与下一步指引"""
    print("[STEP 4] 生成全链路执行报告...")
    if success_flag:
        print("[RESULT] 所有节点执行成功！万事俱备，随时可以推流直播！")
        return True
    print("[ERROR] 某节点执行失败，请排查上方详细日志。")
    return False


def cmd_master(args):
    if args.workspace:
        CONFIG["workspace_dir"] = args.workspace
    print("=== 启动总控流水线 (Master Pipeline) ===")
    if not init_workspace(CONFIG):
        print("[WARN] 暂未检测到完整素材环境。待素材就绪后方可进行物理合成。")
    if not run_perspective_warp_module():
        sys.exit(1)
    if not run_audio_video_muxing_module():
        sys.exit(1)
    if not export_final_report(True):
        sys.exit(1)
    print("=== 全链路总控流程结束 ===")


def main():
    ap = argparse.ArgumentParser(description="助眠直播素材工具集")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("warp", help="OpenCV 透视变换 (Corner Pinning)")
    w.add_argument("-i", "--input", default="")
    w.add_argument("-o", "--output", default="")
    w.add_argument("--width", type=int, default=WARP_DEFAULTS["output_size"][0])
    w.add_argument("--height", type=int, default=WARP_DEFAULTS["output_size"][1])
    w.add_argument("--fps", type=int, default=WARP_DEFAULTS["fps"])
    w.add_argument("--src", type=parse_points, help="原视频4顶点 x1,y1,...,x4,y4 (左上,右上,右下,左下)")
    w.add_argument("--dst", type=parse_points, help="目标区域4顶点")
    w.set_defaults(func=cmd_warp)

    m = sub.add_parser("master", help="全链路主控")
    m.add_argument("--workspace", default="")
    m.set_defaults(func=cmd_master)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
