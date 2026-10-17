#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import pyperclip
import pandas as pd
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# 配置文件路径
SCRIPT_RESOURCE_FILE = r"E:\assets\sanyan\script_resource.xlsx"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 提示词文件路径
PROMPT_FILES = {
    "content": os.path.join(SCRIPT_DIR, "深夜提示词.txt"),
    "character": os.path.join(SCRIPT_DIR, "图片提示词.txt"),
    "youtube": os.path.join(SCRIPT_DIR, "标题提示词.txt")
}

# 全局变量存储当前选中的文件信息
current_selection = {"title": "", "path": ""}
global_input_text = ""  # 记录「生成角色」时的文本，供「生成YouTube信息」复用


def load_excel_titles():
    """读取 Excel 文件，返回 cn_rewrite 不是 'yes' 的前10个标题"""
    try:
        if not os.path.exists(SCRIPT_RESOURCE_FILE):
            print(f"Excel file not found: {SCRIPT_RESOURCE_FILE}")
            return []

        df = pd.read_excel(SCRIPT_RESOURCE_FILE)
        print(f"Excel loaded, total rows: {len(df)}")
        print(f"Columns: {list(df.columns)}")

        # 筛选 cn_rewrite 不是 'yes' 的行
        filtered_df = df[df['cn_rewrite'] != 'yes']
        print(f"Filtered rows (cn_rewrite != 'yes'): {len(filtered_df)}")

        # 取前10个，返回 title 和 path
        titles_data = []
        for _, row in filtered_df.head(10).iterrows():
            title = str(row.get("title", "")).strip()
            path = str(row.get("path", "")).strip()
            print(f"Adding: title='{title}', path='{path}'")
            titles_data.append({
                "title": title,
                "path": path
            })

        print(f"Total titles loaded: {len(titles_data)}")
        return titles_data
    except Exception as e:
        print(f"Error loading Excel: {e}")
        import traceback
        traceback.print_exc()
        return []


def read_file_content(file_path):
    """读取文件内容"""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return ""


def save_content(content, base_path):
    """保存内容到文件"""
    try:
        base_name = os.path.splitext(base_path)[0]

        # 判断是否为 JSON 格式
        try:
            content_json = json.loads(content)
            is_json = True
        except:
            is_json = False

        if is_json:
            # JSON 格式：合并到 _glossary.json
            glossary_file = f"{base_name}_glossary.json"
            existing_data = {}

            if os.path.exists(glossary_file):
                with open(glossary_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)

            # 合并 JSON（新的覆盖旧的同名 key）
            existing_data.update(content_json)

            with open(glossary_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)

            return f"已保存到 {glossary_file}"
        else:
            # 文本格式：保存到 _cn.txt
            cn_file = f"{base_name}_cn.txt"
            with open(cn_file, 'w', encoding='utf-8') as f:
                f.write(content)

            return f"已保存到 {cn_file}"

    except Exception as e:
        return f"保存失败: {e}"


def copy_to_clipboard(prompt_type, content):
    """将提示词 + 内容复制到剪贴板"""
    try:
        prompt_file = PROMPT_FILES.get(prompt_type)
        if not prompt_file or not os.path.exists(prompt_file):
            return f"提示词文件不存在: {prompt_file}", ""

        prompt_content = read_file_content(prompt_file)
        combined_content = prompt_content + "\n\n" + content

        pyperclip.copy(combined_content)

        # 返回组合后的内容，用于前端缓存
        return f"已复制到剪贴板 ({prompt_type})", combined_content

    except Exception as e:
        return f"复制失败: {e}", ""


@app.route('/')
def index():
    """主页面"""
    titles = load_excel_titles()
    return render_template('editor.html', titles=titles)


@app.route('/api/load', methods=['POST'])
def load_content():
    """载入文件内容"""
    global current_selection

    data = request.json
    title = data.get('title', '')
    path = data.get('path', '')

    print(f"Load request: title='{title}', path='{path}'")

    current_selection = {"title": title, "path": path}

    if not path:
        print("Error: path is empty")
        return jsonify({"success": False, "message": "路径为空"})

    # 直接读取 path 指向的原始文件内容
    print(f"Looking for file: {path}")
    print(f"File exists: {os.path.exists(path)}")

    content = read_file_content(path)
    print(f"Content length: {len(content)} characters")

    return jsonify({
        "success": True,
        "content": content,
        "message": f"已载入: {title} (文件: {path})"
    })


@app.route('/api/paste', methods=['POST'])
def paste_content():
    """粘贴剪贴板内容"""
    try:
        clipboard_content = pyperclip.paste()
        # 注意：粘贴操作不应该清空 current_selection，保持当前选择的标题
        return jsonify({
            "success": True,
            "content": clipboard_content,
            "message": "已粘贴剪贴板内容"
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"粘贴失败: {e}"})


@app.route('/api/save', methods=['POST'])
def save_file():
    """保存文件"""
    global current_selection

    data = request.json
    content = data.get('content', '')
    title = data.get('title', '')
    path = data.get('path', '')

    print(f"Save request: title='{title}', path='{path}'")
    print(f"Content length: {len(content)} characters")

    # 更新全局选择状态
    if title and path:
        current_selection = {"title": title, "path": path}

    if not path:
        print("Error: No path provided")
        return jsonify({"success": False, "message": "请先选择一个标题"})

    result = save_content(content, path)
    print(f"Save result: {result}")

    return jsonify({
        "success": True,
        "message": result
    })


@app.route('/api/generate', methods=['POST'])
def generate_prompt():
    """生成提示词"""
    global global_input_text

    data = request.json
    prompt_type = data.get('type', '')  # content, character, youtube
    content = data.get('content', '')

    if prompt_type == "character":
        # 「生成角色」→ 使用当前文本框内容，并记录备用
        global_input_text = content
        use_content = content
    elif prompt_type == "youtube":
        # 「生成YouTube信息」→ 复用「生成角色」时记录的文本
        use_content = global_input_text if global_input_text else content
    else:
        use_content = content

    message, generated_content = copy_to_clipboard(prompt_type, use_content)

    return jsonify({
        "success": True,
        "message": message,
        "generated_content": generated_content  # 返回生成的完整内容
    })


@app.route('/api/complete', methods=['POST'])
def complete_task():
    """标记任务为完成"""
    global current_selection

    data = request.json
    title = data.get('title', '')
    path = data.get('path', '')

    print(f"Complete request: title='{title}', path='{path}'")

    if not path:
        return jsonify({"success": False, "message": "路径为空"})

    try:
        if not os.path.exists(SCRIPT_RESOURCE_FILE):
             return jsonify({"success": False, "message": f"Excel文件未找到: {SCRIPT_RESOURCE_FILE}"})

        # 读取 Excel
        df = pd.read_excel(SCRIPT_RESOURCE_FILE)
        
        # 查找匹配的行 (优先匹配 path，因为 path 更具唯一性)
        mask = (df['path'] == path)
        
        if mask.any():
            df.loc[mask, 'cn_rewrite'] = 'yes'
            # 保存回 Excel
            df.to_excel(SCRIPT_RESOURCE_FILE, index=False)
            print(f"Marked as complete in Excel: {title}")
            return jsonify({"success": True, "message": f"已标记为完成: {title}"})
        else:
            print(f"Could not find matching row for: {title} ({path})")
            return jsonify({"success": False, "message": f"未在Excel中找到匹配项: {title}"})

    except Exception as e:
        print(f"Error updating Excel: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"更新失败: {e}"})


if __name__ == '__main__':
    print("启动编辑器...")
    print(f"Excel 文件: {SCRIPT_RESOURCE_FILE}")
    print(f"提示词目录: {SCRIPT_DIR}")
    print("打开浏览器访问: http://localhost:5000")

    app.run(debug=True, host='localhost', port=5000)