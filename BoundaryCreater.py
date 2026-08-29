import numpy as np
import os
import re
from scipy.spatial import cKDTree

# ==================== 可配置路径 ====================
# 请根据实际需要修改以下目录
INPUT_DIR = r"D:\DeXin\170\111\jisuan\5-赋FB2_fy"          # 输入数据（点云、多段线）所在目录
OUTPUT_DIR = r"D:\DeXin\170\111\jisuan\5-赋FB2_fy"         # 输出结果存放目录
# ==================== 默认参数 ====================
DEFAULT_POINT_CLOUD = "COP3.txt"      # 点云文件名（位于 INPUT_DIR 下）
DEFAULT_XY_TOL = 0.01                 # 去重容差，输入 0 表示跳过
DEFAULT_LINE_TOL = 2
DEFAULT_OUTPUT_PREFIX = "B"
# =================================================


def read_point_cloud(filename):
    """读取点云，返回 (N,3) 数组，列依次为 X,Y,Z"""
    points = []
    # 若 filename 不是绝对路径，则与 INPUT_DIR 拼接
    if not os.path.isabs(filename):
        filename = os.path.join(INPUT_DIR, filename)
    with open(filename, 'r') as f:
        lines = f.readlines()
    # 判断第一行是否为点数（单个整数）
    first = lines[0].strip().split()
    start = 0
    if len(first) == 1 and first[0].isdigit():
        start = 1
    for line in lines[start:]:
        parts = line.strip().split()
        if len(parts) >= 4:
            try:
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
                points.append([x, y, z])
            except ValueError:
                continue
    return np.array(points, dtype=np.float64)


def read_polyline(filename):
    """读取多段线，返回 (M,2) 数组"""
    pts = []
    if not os.path.isabs(filename):
        filename = os.path.join(INPUT_DIR, filename)
    with open(filename, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    x = float(parts[0])
                    y = float(parts[1])
                    pts.append([x, y])
                except ValueError:
                    continue
    return np.array(pts, dtype=np.float64)


def filter_points_by_xy_tolerance(points, tol):
    """XY 去重，仅保留 Z 最大的点"""
    if tol <= 0 or len(points) == 0:
        return points
    xy = points[:, :2]
    z = points[:, 2]
    sorted_idx = np.argsort(-z)  # Z 降序
    keep = np.ones(len(points), dtype=bool)
    tree = cKDTree(xy)
    for idx in sorted_idx:
        if keep[idx]:
            neighbors = tree.query_ball_point(xy[idx], tol)
            for j in neighbors:
                if j != idx:
                    keep[j] = False
    return points[keep]


def point_to_polyline_distance(point, polyline):
    """
    计算点 (x,y) 到多段线的最短距离及弧长参数。
    返回 (距离, 弧长)
    """
    p = np.array(point[:2])
    M = len(polyline)
    if M < 2:
        return np.inf, 0.0
    seg_len = np.linalg.norm(np.diff(polyline, axis=0), axis=1)
    cum_len = np.concatenate(([0], np.cumsum(seg_len)))

    min_dist = np.inf
    arc_pos = 0.0
    for i in range(M - 1):
        A = polyline[i]
        B = polyline[i + 1]
        AB = B - A
        ab_len = seg_len[i]
        if ab_len == 0:
            continue
        t = np.dot(p - A, AB) / (ab_len * ab_len)
        t = np.clip(t, 0.0, 1.0)
        proj = A + t * AB
        dist = np.linalg.norm(p - proj)
        if dist < min_dist:
            min_dist = dist
            arc_pos = cum_len[i] + t * ab_len
    return min_dist, arc_pos


def extract_boundary_points(points, polyline, line_tol):
    """
    提取满足距离阈值的点，返回 (N, 3) 数组 (X,Y,Z) 和对应的距离列表
    """
    if len(points) == 0 or len(polyline) < 2:
        return np.empty((0, 3)), []

    # 计算所有点到多段线的距离和弧长
    all_dists = []
    all_arcs = []
    for pt in points:
        dist, arc = point_to_polyline_distance(pt, polyline)
        all_dists.append(dist)
        all_arcs.append(arc)

    # 筛选
    results = []
    kept_dists = []
    for i, pt in enumerate(points):
        if all_dists[i] <= line_tol:
            results.append((pt[0], pt[1], pt[2], all_arcs[i]))
            kept_dists.append(all_dists[i])

    if not results:
        return np.empty((0, 3)), kept_dists

    # 按弧长排序
    results.sort(key=lambda x: x[3])
    out_xyz = np.array([[x, y, z] for x, y, z, _ in results], dtype=np.float64)
    return out_xyz, kept_dists


def write_output(filename, pts_xyz):
    """输出格式：第一行为点数，后续每行 序号 X Y Z"""
    # 若 filename 不是绝对路径，则与 OUTPUT_DIR 拼接
    if not os.path.isabs(filename):
        filename = os.path.join(OUTPUT_DIR, filename)
    # 确保输出目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        f.write(f"{len(pts_xyz)}\n")
        for i, (x, y, z) in enumerate(pts_xyz, start=1):
            f.write(f"{i}\t{x:.6f}\t{y:.6f}\t{z:.6f}\n")


def main():
    print("======= 点云边界提取程序 (可配置目录版) =======")
    print(f"输入目录: {os.path.abspath(INPUT_DIR)}")
    print(f"输出目录: {os.path.abspath(OUTPUT_DIR)}")

    # 输入点云文件
    pc_file = input(f"请输入点云文件名（默认 {DEFAULT_POINT_CLOUD}，可含相对路径）: ").strip()
    if not pc_file:
        pc_file = DEFAULT_POINT_CLOUD
    # 构建完整路径并检查存在性
    full_pc = pc_file if os.path.isabs(pc_file) else os.path.join(INPUT_DIR, pc_file)
    if not os.path.exists(full_pc):
        print(f"错误：文件 {full_pc} 不存在！")
        return

    xy_tol_input = input(f"请输入XY去重容差（默认 {DEFAULT_XY_TOL}，输入0跳过去重）: ").strip()
    xy_tol = float(xy_tol_input) if xy_tol_input else DEFAULT_XY_TOL

    line_tol_input = input(f"请输入边界匹配容差（默认 {DEFAULT_LINE_TOL}）: ").strip()
    line_tol = float(line_tol_input) if line_tol_input else DEFAULT_LINE_TOL

    print("正在读取点云...")
    all_points = read_point_cloud(full_pc)  # 直接传入完整路径
    print(f"原始点数：{len(all_points)}")
    if len(all_points) == 0:
        print("点云为空，请检查文件格式。")
        return

    # 打印点云范围
    xmin, xmax = np.min(all_points[:, 0]), np.max(all_points[:, 0])
    ymin, ymax = np.min(all_points[:, 1]), np.max(all_points[:, 1])
    print(f"点云 X 范围: {xmin:.2f} ~ {xmax:.2f}")
    print(f"点云 Y 范围: {ymin:.2f} ~ {ymax:.2f}")

    if xy_tol > 0:
        print(f"正在去重（容差 {xy_tol}）...")
        filtered = filter_points_by_xy_tolerance(all_points, xy_tol)
        print(f"去重后点数：{len(filtered)}")
    else:
        filtered = all_points
        print("跳过XY去重。")

    # ---------- 输出去重后的点云文件，便于检查 ----------
    out_removal = "PointsRemoval.txt"
    write_output(out_removal, filtered)
    print(f"已输出去重后的点云文件 {out_removal}，点数：{len(filtered)}")
    # ---------------------------------------------------

    # 在 INPUT_DIR 中查找所有 数字.txt 文件
    pattern = re.compile(r'^(\d+)\.txt$')
    files = []
    # 列出输入目录下的文件
    try:
        for f in os.listdir(INPUT_DIR):
            m = pattern.match(f)
            if m:
                # 排除点云文件本身（避免误匹配）
                if os.path.abspath(os.path.join(INPUT_DIR, f)) != os.path.abspath(full_pc):
                    files.append((int(m.group(1)), f))
    except FileNotFoundError:
        print(f"错误：输入目录 {INPUT_DIR} 不存在！")
        return

    files.sort()

    if not files:
        print("在输入目录中未找到任何数字.txt的多段线文件。")
        return

    print(f"找到 {len(files)} 个多段线文件：{', '.join([f[1] for f in files])}\n")

    for num, fname in files:
        print(f"=== 处理 {fname} ===")
        polyline = read_polyline(fname)  # 内部会拼接 INPUT_DIR
        if len(polyline) < 2:
            print(f"  警告：{fname} 顶点数少于2，跳过")
            continue

        # 打印多段线范围
        pxmin, pxmax = np.min(polyline[:, 0]), np.max(polyline[:, 0])
        pymin, pymax = np.min(polyline[:, 1]), np.max(polyline[:, 1])
        print(f"  多段线 X 范围: {pxmin:.2f} ~ {pxmax:.2f}")
        print(f"  多段线 Y 范围: {pymin:.2f} ~ {pymax:.2f}")

        # 提取边界点（使用固定容差）
        boundary_xyz, dists = extract_boundary_points(filtered, polyline, line_tol)
        out_name = f"{DEFAULT_OUTPUT_PREFIX}{num}.txt"
        write_output(out_name, boundary_xyz)
        print(f"  提取到 {len(boundary_xyz)} 个边界点，已写入 {out_name}")

        # 打印距离统计（仅对筛选出的点，如果有的话）
        if len(dists) > 0:
            print(f"  筛选点距离统计: 最小={np.min(dists):.4f}, 最大={np.max(dists):.4f}, 平均={np.mean(dists):.4f}")
        else:
            print("  未提取到任何点！")

        # 打印全部点到该线的距离分布（帮助判断容差是否合理）
        all_dists = []
        for pt in filtered:
            d, _ = point_to_polyline_distance(pt, polyline)
            all_dists.append(d)
        print(
            f"  全部点到该线距离: 最小={np.min(all_dists):.4f}, 最大={np.max(all_dists):.4f}, 平均={np.mean(all_dists):.4f}")
        print()

    print("全部处理完成！")


if __name__ == "__main__":
    main()