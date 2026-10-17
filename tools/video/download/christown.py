"""
使用用户自定义 KML 多边形区域获取基督城地址。
逻辑：场景1（CBD多边形内50条），场景2（全市交通枢纽20条）。
"""

import random
import requests

# ==================== 配置部分 ====================
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# 根据你提供的 KML 坐标转换 (格式: 纬度 经度)
# 注意：OSM poly 过滤不需要最后一个重复点
CBD_POLY_COORDS = (
    "-43.520721  172.6504781"
    "-43.5207833 172.6256731"
    "-43.5400428 172.6254585"
    "-43.5399495 172.6506498"
)



# 场景2：交通枢纽的搜索范围（全市）
CITY_BBOX = "(-43.60,172.45,-43.40,172.80)"

# 抽样数量
COUNT_CBD = 80
COUNT_HOTSPOT = 20

HEADERS = {
    "User-Agent": "PreciseAddressTool/4.0",
    "Content-Type": "application/x-www-form-urlencoded"
}
# ==================================================

def fetch_overpass_data(query_body):
    """
    底层函数：执行 Overpass 查询并处理响应。
    """
    full_query = f"[out:json][timeout:90];({query_body});out center;"
    print(f"[日志] 正在请求 API...")
    
    try:
        response = requests.post(OVERPASS_URL, data={'data': full_query}, headers=HEADERS, timeout=90)
        if response.status_code != 200:
            print(f"[错误] 服务器返回状态码: {response.status_code}")
            return None
        return response.json().get('elements', [])
    except Exception as e:
        print(f"[错误] 网络请求异常: {e}")
        return None

def extract_addresses(elements, prefix=""):
    """
    底层函数：从元素列表中清洗出唯一地址。
    """
    address_list = []
    for el in elements:
        t = el.get('tags', {})
        house = t.get('addr:housenumber')
        street = t.get('addr:street')
        name = t.get('name')
        
        if house and street:
            address_list.append(f"{house} {street}")
        elif name and street:
            address_list.append(f"{name}, {street}")
        elif name:
            address_list.append(f"{name}")

    unique_addresses = list(set(address_list))
    print(f"[日志] {prefix} 解析到 {len(unique_addresses)} 条唯一地址。")
    return unique_addresses

def get_cbd_scenario():
    """
    逻辑分层：专门获取你画的那个框内的地址。
    """
    print("[步骤 1] 获取自定义 CBD 多边形区域内的地址...")
    # 使用 poly 过滤符
    query = f'nwr["addr:housenumber"](poly:"{CBD_POLY_COORDS}");'
    
    elements = fetch_overpass_data(query)
    if not elements:
        print("[错误] 无法在指定多边形内找到地址数据。")
        return []
        
    all_addresses = extract_addresses(elements, "CBD")
    
    if len(all_addresses) < COUNT_CBD:
        print(f"[警告] CBD 区域地址样本较少，将返回全部 {len(all_addresses)} 条。")
        return all_addresses
    
    return random.sample(all_addresses, COUNT_CBD)

def get_hotspot_scenario():
    """
    逻辑分层：获取基督城主要交通枢纽/热点。
    """
    print("[步骤 2] 获取全市范围内的交通枢纽与热点区域...")
    # 搜索：车站、机场、大型购物中心
    types = [
        'node["amenity"="bus_station"]',
        'node["railway"="station"]',
        'node["aeroway"="terminal"]',
        'node["shop"="mall"]'
    ]
    query = "".join([f"{t}{CITY_BBOX};" for t in types])
    
    elements = fetch_overpass_data(query)
    if not elements:
        print("[错误] 无法找到热点区域数据。")
        return []
        
    all_addresses = extract_addresses(elements, "Hotspot")
    
    if len(all_addresses) < COUNT_HOTSPOT:
        return all_addresses
        
    return random.sample(all_addresses, COUNT_HOTSPOT)

def main():
    """
    主控函数：仅负责流程调度。
    """
    print("=== 启动精准地址获取流程 ===")
    
    # 获取 CBD
    final_cbd = get_cbd_scenario()
    
    # 获取热点
    final_hotspot = get_hotspot_scenario()
    
    # 结果展示
    print("\n" + "="*50)
    print(f"场景一：CBD 区域地址 (共 {len(final_cbd)} 条)")
    for i, addr in enumerate(final_cbd, 1):
        print(f"CBD_{i:02d}: {addr}")
        
    print("\n场景二：交通枢纽/热点地址 (共 {len(final_hotspot)} 条)")
    for i, addr in enumerate(final_hotspot, 1):
        print(f"HOT_{i:02d}: {addr}")
    print("="*50)
    
    print("\n=== 所有任务已完成 ===")

if __name__ == "__main__":
    main()