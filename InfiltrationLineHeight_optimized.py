import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import os
import sys
import time
import unicodedata


# 程序所在目录。输入文件和输出文件默认都放在这里。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_HEADER = (
    '序号\tX\tY\t监测值\t计算值\t监测值-计算值\t相对误差\t查询点名称'
)

# ==================== 默认配置 ====================
DEFAULT_CONFIG = {
    'input_dir': r'D:\DeXin\170\111\jisuan\6反演',                # 默认在程序所在目录查找输入文件
    'output_dir': r'D:\DeXin\170\111\jisuan\6反演',               # 默认将结果写入程序所在目录
    'node_file': 'FIELD_20.txt',     # 节点文件名
    'query_file': 'query_pointsNew.txt',     # 查询点文件名
    'output_file': 'interpolated_headsNew.txt', # 输出文件名
    'search_radius': None,                # 初始搜索半径，None 自动估算
    'min_points': 8,                      # 插值所需最少邻近浸润点数
    'max_radius': None,                   # 最大搜索半径，None 自动设为初始半径10倍
    'merge_tol': 0.01,                    # XY 坐标合并容差（用于分组铅直线）
    'idw_power': 2.0,                     # 反距离加权幂指数
    'radius_multiplier': 1.5,             # 半径扩大倍数
    'max_expand_iter': 20,                # 最大扩大次数
}


def resolve_path(base_dir, path_value):
    """将文件名或路径解析为可直接访问的路径。"""
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(base_dir, path_value)


def validate_config(config):
    """检查会影响空间搜索和插值稳定性的配置项。"""
    positive_values = {
        'merge_tol': config['merge_tol'],
        'idw_power': config['idw_power'],
    }
    for name, value in positive_values.items():
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} 必须是大于 0 的有限数值")

    if config['search_radius'] is not None:
        radius = config['search_radius']
        if not np.isfinite(radius) or radius <= 0:
            raise ValueError("search_radius 必须为 None 或大于 0 的有限数值")

    if config['max_radius'] is not None:
        max_radius = config['max_radius']
        if not np.isfinite(max_radius) or max_radius <= 0:
            raise ValueError("max_radius 必须为 None 或大于 0 的有限数值")

    if (config['search_radius'] is not None and config['max_radius'] is not None
            and config['max_radius'] < config['search_radius']):
        raise ValueError("max_radius 不能小于 search_radius")

    if not isinstance(config['min_points'], (int, np.integer)) or config['min_points'] < 1:
        raise ValueError("min_points 必须是大于或等于 1 的整数")
    if not np.isfinite(config['radius_multiplier']) or config['radius_multiplier'] <= 1:
        raise ValueError("radius_multiplier 必须是大于 1 的有限数值")
    if (not isinstance(config['max_expand_iter'], (int, np.integer))
            or config['max_expand_iter'] < 0):
        raise ValueError("max_expand_iter 必须是大于或等于 0 的整数")

# ==================== 读取节点数据 ====================
def read_node_file(filepath):
    """
    读取有限元渗流计算结果文件，返回节点数组 (N, 5): [id, x, y, z, h]
    文件格式：第一行为节点总数（取第一个数字），后续每行5个数据
    """
    print(f"  正在读取节点文件: {filepath}")
    with open(filepath, 'r', encoding='utf-8') as f:
        first_line = f.readline().strip()
        try:
            np_count = int(first_line.split()[0])
        except (IndexError, ValueError):
            raise ValueError("节点文件第一行必须包含节点总数")

        # 使用正则表达式 \s+ 作为分隔符，兼容任意空白字符
        data = pd.read_csv(f, sep=r'\s+', header=None,
                           nrows=np_count, names=['id', 'x', 'y', 'z', 'h'],
                           engine='python')

    if len(data) != np_count:
        raise ValueError(f"节点文件声明 {np_count} 个节点，实际只读取到 {len(data)} 个")

    numeric_data = data[['id', 'x', 'y', 'z', 'h']].apply(
        pd.to_numeric, errors='coerce'
    )
    nodes = numeric_data.to_numpy(dtype=float)
    if not np.isfinite(nodes).all():
        raise ValueError("节点数据包含非数值、空值或无穷值")

    print(f"  成功读取 {len(nodes)} 个节点")
    return nodes


def group_xy_with_tolerance(xy, tol):
    """
    按欧氏距离容差合并 XY 坐标。

    每个点与相邻网格中的组代表点比较，并归入距离不超过 tol 的最近组，
    避免直接按小数位四舍五入造成的分组边界问题。
    """
    unique_xy, inverse = np.unique(xy, axis=0, return_inverse=True)
    buckets = {}
    representatives = []
    unique_group_ids = np.empty(len(unique_xy), dtype=np.int64)
    tol_sq = tol * tol

    for point_index, (x, y) in enumerate(unique_xy):
        cell = (int(np.floor(x / tol)), int(np.floor(y / tol)))
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                candidates.extend(buckets.get((cell[0] + dx, cell[1] + dy), ()))

        best_group = None
        best_distance_sq = None
        for group_id in candidates:
            rep_x, rep_y = representatives[group_id]
            distance_sq = (x - rep_x) ** 2 + (y - rep_y) ** 2
            if distance_sq <= tol_sq and (
                    best_distance_sq is None or distance_sq < best_distance_sq):
                best_group = group_id
                best_distance_sq = distance_sq

        if best_group is None:
            best_group = len(representatives)
            representatives.append((x, y))
            buckets.setdefault(cell, []).append(best_group)

        unique_group_ids[point_index] = best_group

    return unique_group_ids[inverse]

# ==================== 提取浸润点 ====================
def extract_infiltration_points(nodes, tol=1e-3, pressure_tol=1e-10):
    """
    从节点数据中提取每个 XY 位置上的浸润高度（压力水头为零的高程）。
    返回浸润点数组 (M, 3): [x, y, z_infil]
    """
    print("  正在提取浸润点（压力水头为零的位置）...")
    df = pd.DataFrame(nodes[:, 1:], columns=['x', 'y', 'z', 'h'])
    df['p'] = df['h'] - df['z']  # 压力水头

    if not np.isfinite(tol) or tol <= 0:
        raise ValueError("XY 合并容差必须是大于 0 的有限数值")
    if not np.isfinite(pressure_tol) or pressure_tol < 0:
        raise ValueError("压力水头容差必须是大于或等于 0 的有限数值")

    df['xy_group'] = group_xy_with_tolerance(df[['x', 'y']].to_numpy(), tol)

    infiltration_points = []
    # 按 XY 分组处理
    grouped = df.groupby('xy_group', sort=False)
    for _, group in grouped:
        # 按 Z 排序
        group_sorted = group.sort_values('z')
        z_vals = group_sorted['z'].values
        p_vals = group_sorted['p'].values

        # 优先处理压力水头恰好为零的节点。
        zero_indices = np.flatnonzero(np.isclose(
            p_vals, 0.0, rtol=0.0, atol=pressure_tol
        ))
        if len(zero_indices) > 0:
            z_infil = z_vals[zero_indices[0]]
        else:
            # 随高程增加，浸润面处的压力水头应由正变负。
            crossings = np.flatnonzero(
                (p_vals[:-1] > pressure_tol) & (p_vals[1:] < -pressure_tol)
            )
            if len(crossings) == 0:
                continue

            # 多个交点时保持原程序语义，取从低到高遇到的第一个交点。
            idx = crossings[0]
            z1, z2 = z_vals[idx], z_vals[idx+1]
            p1, p2 = p_vals[idx], p_vals[idx+1]
            z_infil = z1 - p1 * (z2 - z1) / (p2 - p1)

        x_avg = group_sorted['x'].mean()
        y_avg = group_sorted['y'].mean()
        infiltration_points.append([x_avg, y_avg, z_infil])

    if len(infiltration_points) == 0:
        raise RuntimeError("未能从节点数据中提取到任何浸润点，请检查数据或合并容差。")

    infil_array = np.array(infiltration_points)
    print(f"  提取到 {len(infil_array)} 个浸润点")
    return infil_array

# ==================== 自动估算搜索半径 ====================
def estimate_radius(points):
    """
    基于浸润点的最近邻距离中位数估计初始搜索半径。
    排除重复坐标产生的零距离后，取中位最近邻距离的 3 倍。
    """
    unique_xy = np.unique(points[:, :2], axis=0)
    if len(unique_xy) < 2:
        return 1.0
    tree = cKDTree(unique_xy)
    dist, _ = tree.query(unique_xy, k=2)
    nn_dist = dist[:, 1]  # 第二近即最近邻
    nn_dist = nn_dist[np.isfinite(nn_dist) & (nn_dist > 1e-12)]
    if len(nn_dist) == 0:
        return 1.0
    median_nn = np.median(nn_dist)
    estimated = max(median_nn * 3.0, 1e-6)
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


def format_output_number(value, suffix='', decimals=4):
    """按指定小数位输出有限数值，缺失或无效数值统一输出 NAN。"""
    if not np.isfinite(value):
        return 'NAN'
    return f"{value:.{decimals}f}{suffix}"


def text_display_width(text, tab_size=8):
    """计算包含中文和制表符的文本显示宽度。"""
    width = 0
    for char in text:
        if char == '\t':
            width += tab_size - width % tab_size
        elif unicodedata.east_asian_width(char) in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def open_output_file(filepath):
    """使用 Windows 默认关联程序打开结果文件。"""
    if not hasattr(os, 'startfile'):
        print(f"  提示: 当前系统不支持自动打开文件，请手动查看: {filepath}")
        return False
    try:
        os.startfile(os.path.abspath(filepath))
    except OSError as exc:
        print(f"  提示: 无法自动打开结果文件，请手动查看: {filepath}（{exc}）")
        return False
    print("  已自动打开结果文件")
    return True

# ==================== 主处理函数 ====================
def process(config, open_output=False):
    start_time = time.time()
    validate_config(config)

    node_path = resolve_path(config['input_dir'], config['node_file'])
    query_path = resolve_path(config['input_dir'], config['query_file'])
    output_path = resolve_path(config['output_dir'], config['output_file'])

    output_parent = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_parent, exist_ok=True)

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
    if max_radius < radius:
        raise ValueError(
            f"最大搜索半径 {max_radius} 不能小于初始搜索半径 {radius}"
        )
    print(f"  最大搜索半径: {max_radius}")

    min_points = config['min_points']
    power = config['idw_power']
    mult = config['radius_multiplier']
    max_iter = config['max_expand_iter']

    # 5. 读取查询点
    print(f"  正在读取查询点文件: {query_path}")
    queries = []
    with open(query_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=4)
            if len(parts) < 5:
                print(
                    f"  警告: 第 {line_num} 行格式错误，应为："
                    "序号 X Y 监测值 名称，跳过"
                )
                continue
            qid = parts[0]
            try:
                x = float(parts[1])
                y = float(parts[2])
                observed = float(parts[3])
            except ValueError:
                print(f"  警告: 第 {line_num} 行坐标或监测值无法解析，跳过")
                continue
            if not np.isfinite(x) or not np.isfinite(y):
                print(f"  警告: 第 {line_num} 行坐标不是有限数值，跳过")
                continue
            if np.isinf(observed):
                print(f"  警告: 第 {line_num} 行监测值不能为无穷值，跳过")
                continue
            name = parts[4]
            queries.append((qid, x, y, observed, name))

    n_queries = len(queries)
    print(f"  共读取 {n_queries} 个查询点")

    # 6. 插值计算
    print("  开始插值计算...")
    results = []
    insufficient_count = 0
    empty_count = 0
    missing_observed_count = 0
    zero_observed_count = 0
    for idx, (qid, xq, yq, observed, name) in enumerate(queries, 1):
        current_radius = radius
        neighbor_indices = tree.query_ball_point([xq, yq], current_radius)

        expand_count = 0
        while (len(neighbor_indices) < min_points
               and current_radius < max_radius
               and expand_count < max_iter):
            next_radius = min(current_radius * mult, max_radius)
            if next_radius <= current_radius:
                break
            current_radius = next_radius
            neighbor_indices = tree.query_ball_point([xq, yq], current_radius)
            expand_count += 1

        if len(neighbor_indices) == 0:
            h_interp = float('nan')
            empty_count += 1
        else:
            neighbor_pts = infiltration_points[neighbor_indices]
            h_interp = idw_interpolate(xq, yq, neighbor_pts, power)
            if len(neighbor_indices) < min_points:
                insufficient_count += 1

        if np.isfinite(observed) and np.isfinite(h_interp):
            difference = observed - h_interp
            if abs(observed) > 1e-12:
                relative_error = abs(h_interp - observed) / abs(observed) * 100.0
            else:
                relative_error = float('nan')
                zero_observed_count += 1
        else:
            difference = float('nan')
            relative_error = float('nan')
            if np.isnan(observed):
                missing_observed_count += 1

        results.append((
            qid, xq, yq, observed, h_interp,
            difference, relative_error, name
        ))

        if idx % 100 == 0 or idx == n_queries:
            elapsed = time.time() - start_time
            print(f"  已处理 {idx}/{n_queries} 个点，耗时 {elapsed:.2f} 秒")

    # 7. 写入结果
    print(f"  正在写入结果到: {output_path}")
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        f.write(OUTPUT_HEADER + '\n')
        f.write('*' * text_display_width(OUTPUT_HEADER) + '\n')
        for (qid, x, y, observed, calculated,
             difference, relative_error, name) in results:
            fields = [
                qid,
                format_output_number(x),
                format_output_number(y),
                format_output_number(observed),
                format_output_number(calculated),
                format_output_number(difference),
                format_output_number(relative_error, '%', decimals=2),
                name,
            ]
            f.write('\t'.join(fields) + '\n')

    total_time = time.time() - start_time
    if insufficient_count:
        print(f"  警告: {insufficient_count} 个查询点使用的邻点少于 {min_points} 个")
    if empty_count:
        print(f"  警告: {empty_count} 个查询点未找到邻点，结果写为 NAN")
    if missing_observed_count:
        print(
            f"  提示: {missing_observed_count} 个查询点暂无监测值，"
            "差值和相对误差写为 NAN"
        )
    if zero_observed_count:
        print(
            f"  提示: {zero_observed_count} 个查询点监测值为 0，"
            "相对误差写为 NAN"
        )
    print(f"  全部完成！总计耗时 {total_time:.2f} 秒")
    if open_output:
        open_output_file(output_path)
    return results

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
            config['node_file'] = node_input

        query_input = input(f"查询点文件名或完整路径 [{config['query_file']}]: ").strip()
        if query_input:
            config['query_file'] = query_input

        output_input = input(f"输出文件名或完整路径 [{config['output_file']}]: ").strip()
        if output_input:
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

    try:
        validate_config(config)
    except ValueError as exc:
        print(f"错误：配置无效：{exc}")
        return 1

    # 检查输入文件
    node_path = resolve_path(config['input_dir'], config['node_file'])
    query_path = resolve_path(config['input_dir'], config['query_file'])
    if not os.path.exists(node_path):
        print(f"错误：节点文件 {node_path} 不存在！")
        return 1
    if not os.path.exists(query_path):
        print(f"错误：查询点文件 {query_path} 不存在！")
        return 1

    try:
        process(config, open_output=True)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误：{exc}")
        return 1
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except ValueError as exc:
        print(f"错误：输入值无效：{exc}")
        sys.exit(1)
