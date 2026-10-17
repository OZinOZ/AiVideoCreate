# ==========================================
# CONFIGURATION
# ==========================================
# 输入与输出的 Excel 文件路径
"""
Excel Data Row Expansion Script (Formula & Format Preserving).

This script reads an input Excel file natively, iterates through rows bottom-up,
and duplicates specific rows based on values in the target column. 
It guarantees that all original Excel formulas are preserved and dynamically
translated (shifted) for the new rows, while keeping all formatting intact.

Strictly layered architecture, top-level configuration, pure functional steps,
and comprehensive console logging. Pylint compliant.
"""

import sys
from typing import Optional
import os
from copy import copy
from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.formula.translate import Translator

# ==========================================
# CONFIGURATION
# ==========================================
# 输入与输出的 Excel 文件路径
INPUT_EXCEL_PATH = r"E:\upwork\GC0222-0225.xlsx"
OUTPUT_EXCEL_PATH = r"E:\upwork\GC0222-0225_expanded.xlsx"

# 【重要】Excel 表头所在的真实行号（openpyxl 中行号从 1 开始计数）
# 例如：如果表头在 Excel 第一行填 1，在第二行填 2
HEADER_ROW_NUMBER = 14

# 目标判断的列名
TARGET_COLUMN = "Car Types/Surge"

# 裂变规则：字典的 Key 是触发条件，Value 是裂变后的新车型列表
# 逻辑：原行会被替换为 Value 列表的第 1 个值，并向下新增行填充后续的值
EXPANSION_RULES = {
    "DiDi Express": ["DiDi Express", "DiDi Travel", "DiDi Max"],
    "UberX": ["UberX", "UberXL", "Uber Max"]
}


# ==========================================
# FUNCTIONS
# ==========================================
def load_excel_workbook(file_path: str) -> Optional[Workbook]:
    """Loads an Excel file strictly retaining formulas and structure."""
    print(f"[INFO] Attempting to load Excel workbook from: '{file_path}'...")
    
    if not os.path.exists(file_path):
        print(f"[ERROR] Failed to load workbook: File '{file_path}' does not exist.")
        return None
        
    try:
        # data_only=False 是默认值，确保读取的是公式而不是只读计算结果
        workbook = load_workbook(file_path)
        print("[SUCCESS] Excel workbook loaded successfully (formulas preserved).")
        return workbook
    except Exception as e:
        print(f"[ERROR] Failed to read Excel workbook due to an exception: {e}")
        return None


def execute_row_expansion(wb: Workbook, header_row: int, target_col_name: str, rules: dict) -> bool:
    """Processes the active worksheet, duplicating rows and translating formulas."""
    print("[INFO] Starting to process and expand rows bottom-up...")
    ws = wb.active
    
    # 1. 查找目标列在第几列
    target_col_idx = None
    for col in range(1, ws.max_column + 1):
        if ws.cell(row=header_row, column=col).value == target_col_name:
            target_col_idx = col
            break
            
    if not target_col_idx:
        print(f"[ERROR] Processing failed: Column '{target_col_name}' not found "
              f"in row {header_row}.")
        return False
        
    print(f"[SUCCESS] Target column '{target_col_name}' found at column index {target_col_idx}.")
    
    # 2. 从下往上遍历所有行（非常重要：只有从下往上插入行，才不会打乱尚未处理的行号）
    rows_processed = 0
    
    try:
        for row_idx in range(ws.max_row, header_row, -1):
            cell_val = ws.cell(row=row_idx, column=target_col_idx).value
            
            if cell_val in rules:
                new_types = rules[cell_val]
                # 需要新插入的行数（比如 1个变2个，则原行改名，再插 1 行）
                num_new_rows = len(new_types) - 1
                
                if num_new_rows > 0:
                    # 在当前行下方插入空行
                    ws.insert_rows(row_idx + 1, num_new_rows)
                    
                    # 复制原行的数据、样式、平移公式到新行
                    for i in range(num_new_rows):
                        new_row_idx = row_idx + 1 + i
                        new_type = new_types[i + 1] # 获取对应的新车型名字
                        
                        for col_idx in range(1, ws.max_column + 1):
                            source_cell = ws.cell(row=row_idx, column=col_idx)
                            target_cell = ws.cell(row=new_row_idx, column=col_idx)
                            
                            # 复制单元格全部样式
                            if source_cell.has_style:
                                target_cell.font = copy(source_cell.font)
                                target_cell.border = copy(source_cell.border)
                                target_cell.fill = copy(source_cell.fill)
                                target_cell.number_format = copy(source_cell.number_format)
                                target_cell.protection = copy(source_cell.protection)
                                target_cell.alignment = copy(source_cell.alignment)
                            
                            # 核心逻辑：区分普通值和公式
                            if source_cell.data_type == 'f':
                                # 翻译（平移）公式，例如把 =A2+B2 翻译成 =A3+B3
                                target_cell.value = Translator(
                                    source_cell.value, origin=source_cell.coordinate
                                ).translate_formula(target_cell.coordinate)
                            else:
                                target_cell.value = source_cell.value
                                
                        # 覆盖新行的目标列名字
                        ws.cell(row=new_row_idx, column=target_col_idx).value = new_type
                        
                # 覆盖原始行的目标列名字为列表的第 1 个值
                ws.cell(row=row_idx, column=target_col_idx).value = new_types[0]
                rows_processed += 1
                
        print(f"[SUCCESS] Data expansion complete. Total target events processed: {rows_processed}.")
        return True
        
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred during row expansion: {e}")
        return False


def save_excel_workbook(wb: Workbook, file_path: str) -> bool:
    """Saves the modified workbook back to an Excel file."""
    print(f"[INFO] Attempting to save expanded workbook to: '{file_path}'...")
    
    try:
        wb.save(file_path)
        print(f"[SUCCESS] File saved successfully to '{file_path}'.")
        return True
    except PermissionError:
        print(f"[ERROR] Save failed: Permission denied. Is '{file_path}' currently open in Excel?")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to save Excel file due to an exception: {e}")
        return False


def main():
    """Main orchestrator function for the Excel processing workflow."""
    print("=== STARTING EXCEL FORMULA-PRESERVING WORKFLOW ===")
    
    # Step 1: 读取底层结构（保留公式）
    workbook = load_excel_workbook(INPUT_EXCEL_PATH)
    if not workbook:
        print("[FATAL] Workflow aborted at data loading stage.")
        sys.exit(1)
        
    # Step 2: 执行裂变与公式平移
    process_status = execute_row_expansion(workbook, HEADER_ROW_NUMBER, TARGET_COLUMN, EXPANSION_RULES)
    if not process_status:
        print("[FATAL] Workflow aborted at data processing stage.")
        sys.exit(1)
        
    # Step 3: 保存输出文件
    save_status = save_excel_workbook(workbook, OUTPUT_EXCEL_PATH)
    if not save_status:
        print("[FATAL] Workflow aborted at data saving stage.")
        sys.exit(1)
        
    print("=== WORKFLOW COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()