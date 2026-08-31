import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import os
import sys
import time

# ==================== 默认配置 ====================
DEFAULT_CONFIG = {
    'input_dir': r'D:\DeXin\170\111\jisuan\6反演',                     # 输入目录
    'output_dir': r'D:\DeXin\170\111\jisuan\6反演',                    # 输出目录
    'node_file': 'FIELD_20.txt',     # 节点文件名
    'query_file': 'query_points.txt',     # 查询点文件名
    'output_file': 'interpolated_heads.txt', # 输出文件名
    'search_radius': None,                # 初始搜索半径，None 自动估算
    'min_points': 8,                      # 插值所需最少邻近浸润点数
    'max_radius': None,                   # 最大搜索半径，None 自动设为初始半径10倍
    'merge_tol': 0.01,                    # XY 坐标合并容差（用于分组铅直线）
    'idw_power': 2.0,                     # 反距离加权幂指数
    'radius_multiplier': 1.5,             # 半径扩大倍数
    'max_expand_iter': 20,                # 最大扩大次数
}

# ==================== 读取节点数据 ====================
def read_node_file(filepath):
    """
    读取有限元渗流计算结果文件，返回节点数组 (N, 5): [id, x, y, z, h]
    文件格式：第一行为节点总数（取第一个数字），后续每行5个数据
    """
    print(f"  正在读取节点文件: {filepath}")
    with open(filepath, 'r') as f:
        first_line = f.readline().strip()
        try:
            np_count = int(first_line.split()[0])
        except (IndexError, ValueError):
            raise ValueError("节点文件第一行必须包含节点总数")

        # 使用正则表达式 \s+ 作为分隔符，兼容任意空白字符
        data = pd.read_csv(f, sep=r'\s+', header=None,
                           nrows=np_count, names=['id', 'x', 'y', 'z', 'h'],
                           engine='python')

    nodes = data[['id', 'x', 'y', 'z', 'h']].values
    print(f"  成功读取 {len(nodes)} 个节点")
    return nodes

# ==================== 提取浸润点 ====================
def extract_infiltration_points(nodes, tol=1e-3):
    """
    从节点数据中提取每个 XY 位置上的浸润高度（压力水头为零的高程）。
    返回浸润点数组 (M, 3): [x, y, z_infil]
    """
    print("  正在提取浸润点（压力水头为零的位置）...")
    df = pd.DataFrame(nodes[:, 1:], columns=['x', 'y', 'z', 'h'])
    df['p'] = df['h'] - df['z']  # 压力水头

    # 根据容差确定 XY 坐标的分组精度
    decimal_places = max(0, int(np.ceil(-np.log10(tol))))
    df['x_key'] = df['x'].round(decimal_places)
    df['y_key'] = df['y'].round(decimal_places)

    infiltration_points = []
    # 按 XY 分组处理
    grouped = df.groupby(['x_key', 'y_key'])
    for (x_key, y_key), group in grouped:
        # 按 Z 排序
        group_sorted = group.sort_values('z')
        z_vals = group_sorted['z'].values
        p_vals = group_sorted['p'].values

        # 寻找压力水头符号变化
        sign_changes = np.where(np.diff(np.sign(p_vals)) != 0)[0]
        if len(sign_changes) > 0:
            # 取第一个符号变化区间进行线性插值
            idx = sign_changes[0]
            z1, z2 = z_vals[idx], z_vals[idx+1]
            p1, p2 = p_vals[idx], p_vals[idx+1]
            # 线性插值求 p=0 的 z
            if p1 != p2:
                z_infil = z1 - p1 * (z2 - z1) / (p2 - p1)
            else:
                z_infil = (z1 + z2) / 2.0  # 理论上不会发生
            # 使用该组的平均 x, y（实际上同一组内 x,y 几乎相同）
            x_avg = group_sorted['x'].iloc[0]
            y_avg = group_sorted['y'].iloc[0]
            infiltration_points.append([x_avg, y_avg, z_infil])

    if len(infiltration_points) == 0:
        raise RuntimeError("未能从节点数据中提取到任何浸润点，请检查数据或合并容差。")

    infil_array = np.array(infiltration_points)
    print(f"  提取到 {len(infil_array)} 个浸润点")
    return infil_array

# ==================== 自动估算搜索半径 ====================
def estimate_radius(points):
    """
    基于浸润点的平均最近邻距离估计初始搜索半径。
    取平均最近邻距离的 3 倍。
    """
    if len(points) < 2:
        return 1.0
    tree = cKDTree(points[:, :2])
    dist, _ = tree.query(points[:, :2], k=2)
    nn_dist = dist[:, 1]  # 第二近即最近邻
    mean_nn = np.mean(nn_dist)
    estimated = max(mean_nn * 3.0, 1e-6)
    print(f"  自动估算初始搜索半径: {estimated:.6f}")
    return estimated

# ==================== 反距离加权插值 ====================
def idw_interpolate(xq, yq, neighbor_points, power=2.0):
    """
    对查询点 (xq, yq) 使用反距离加权插值。
    neighbor_points: (K, 3) 数组 [x, y, z_infil]
    """
    if len(neighbor_points) == 0:
        return float('nan')

    distances = np.sqrt((neighbor_points[:, 0] - xq)**2 +
                         (neighbor_points[:, 1] - yq)**2)

    # 若有重合点，直接返回该点浸润高度
    zero_mask = distances < 1e-12
    if np.any(zero_mask):
        return neighbor_points[zero_mask][0, 2]

    distances = np.maximum(distances, 1e-12)
    weights = 1.0 / (distances ** power)
    return np.sum(weights * neighbor_points[:, 2]) / np.sum(weights)

# ==================== 主处理函数 ====================
def process(config):
    start_time = time.time()

    node_path = os.path.join(config['input_dir'], config['node_file'])
    query_path = os.path.join(config['input_dir'], config['query_file'])
    output_path = os.path.join(config['output_dir'], config['output_file'])

    os.makedirs(config['output_dir'], exist_ok=True)

    # 1. 读取节点
    nodes = read_node_file(node_path)

    # 2. 提取浸润点
    infiltration_points = extract_infiltration_points(nodes, tol=config['merge_tol'])

    # 3. 构建 KD 树
    print("  正在构建 KD 树...")
    tree = cKDTree(infiltration_points[:, :2])

    # 4. 确定搜索半径
    if config['search_radius'] is None:
        radius = estimate_radius(infiltration_points)
    else:
        radius = config['search_radius']
        print(f"  使用指定初始搜索半径: {radius}")

    if config['max_radius'] is None:
        max_radius = radius * 10.0
    else:
        max_radius = config['max_radius']
    print(f"  最大搜索半径: {max_radius}")

    min_points = config['min_points']
    power = config['idw_power']
    mult = config['radius_multiplier']
    max_iter = config['max_expand_iter']

    # 5. 读取查询点
    print(f"  正在读取查询点文件: {query_path}")
    queries = []
    with open(query_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=3)
            if len(parts) < 3:
                print(f"  警告: 第 {line_num} 行格式错误，跳过")
                continue
            qid = parts[0]
            try:
                x = float(parts[1])
                y = float(parts[2])
            except ValueError:
                print(f"  警告: 第 {line_num} 行坐标无法解析，跳过")
                continue
            comment = parts[3] if len(parts) == 4 else ''
            queries.append((qid, x, y, comment))

    n_queries = len(queries)
    print(f"  共读取 {n_queries} 个查询点")

    # 6. 插值计算
    print("  开始插值计算...")
    results = []
    for idx, (qid, xq, yq, comment) in enumerate(queries, 1):
        current_radius = radius
        neighbor_indices = tree.query_ball_point([xq, yq], current_radius)

        expand_count = 0
        while len(neighbor_indices) < min_points and current_radius < max_radius and expand_count < max_iter:
            current_radius *= mult
            neighbor_indices = tree.query_ball_point([xq, yq], current_radius)
            expand_count += 1

        if len(neighbor_indices) == 0:
            h_interp = float('nan')
        else:
            neighbor_pts = infiltration_points[neighbor_indices]
            h_interp = idw_interpolate(xq, yq, neighbor_pts, power)

        results.append((qid, xq, yq, h_interp, comment))

        if idx % 100 == 0 or idx == n_queries:
            elapsed = time.time() - start_time
            print(f"  已处理 {idx}/{n_queries} 个点，耗时 {elapsed:.2f} 秒")

    # 7. 写入结果
    print(f"  正在写入结果到: {output_path}")
    with open(output_path, 'w') as f:
        for qid, x, y, h, comment in results:
            f.write(f"{qid}\t{x:.6f}\t{y:.6f}\t{h:.6f}\t{comment}\n")

    total_time = time.time() - start_time
    print(f"  全部完成！总计耗时 {total_time:.2f} 秒")

# ==================== 控制台交互 ====================
def main():
    config = DEFAULT_CONFIG.copy()

    print("===== 渗流浸润线插值程序 =====")
    print("当前默认配置：")
    for key, value in config.items():
        print(f"  {key}: {value}")

    use_default = input("是否使用默认配置？(y/n, 直接回车默认 y): ").strip().lower()
    if use_default == 'n':
        print("请输入修改项（直接回车保留默认值）：")

        config['input_dir'] = input(f"输入目录 [{config['input_dir']}]: ").strip() or config['input_dir']
        config['output_dir'] = input(f"输出目录 [{config['output_dir']}]: ").strip() or config['output_dir']

        node_input = input(f"节点文件名或完整路径 [{config['node_file']}]: ").strip()
        if node_input:
            if os.path.isabs(node_input) or os.path.dirname(node_input):
                config['node_file'] = node_input
                config['input_dir'] = ''
            else:
                config['node_file'] = node_input

        query_input = input(f"查询点文件名或完整路径 [{config['query_file']}]: ").strip()
        if query_input:
            if os.path.isabs(query_input) or os.path.dirname(query_input):
                config['query_file'] = query_input
                config['input_dir'] = ''
            else:
                config['query_file'] = query_input

        output_input = input(f"输出文件名或完整路径 [{config['output_file']}]: ").strip()
        if output_input:
            if os.path.isabs(output_input) or os.path.dirname(output_input):
                config['output_file'] = output_input
                config['output_dir'] = ''
            else:
                config['output_file'] = output_input

        radius_input = input(f"初始搜索半径（None 表示自动） [{config['search_radius']}]: ").strip()
        if radius_input.lower() == 'none':
            config['search_radius'] = None
        elif radius_input:
            config['search_radius'] = float(radius_input)

        min_points_input = input(f"最少节点数 [{config['min_points']}]: ").strip()
        if min_points_input:
            config['min_points'] = int(min_points_input)

        max_radius_input = input(f"最大搜索半径（None 表示自动） [{config['max_radius']}]: ").strip()
        if max_radius_input.lower() == 'none':
            config['max_radius'] = None
        elif max_radius_input:
            config['max_radius'] = float(max_radius_input)

        merge_tol_input = input(f"合并容差 [{config['merge_tol']}]: ").strip()
        if merge_tol_input:
            config['merge_tol'] = float(merge_tol_input)

        idw_power_input = input(f"IDW 幂指数 [{config['idw_power']}]: ").strip()
        if idw_power_input:
            config['idw_power'] = float(idw_power_input)

        radius_mult_input = input(f"半径扩大倍数 [{config['radius_multiplier']}]: ").strip()
        if radius_mult_input:
            config['radius_multiplier'] = float(radius_mult_input)

    # 检查输入文件
    node_path = os.path.join(config['input_dir'], config['node_file'])
    query_path = os.path.join(config['input_dir'], config['query_file'])
    if not os.path.exists(node_path):
        print(f"错误：节点文件 {node_path} 不存在！")
        sys.exit(1)
    if not os.path.exists(query_path):
        print(f"错误：查询点文件 {query_path} 不存在！")
        sys.exit(1)

    process(config)

if __name__ == '__main__':
    main()