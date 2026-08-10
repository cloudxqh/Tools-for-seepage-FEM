import os

def generate_initial_bln(f1, input_dir, output_dir):
    """生成第一个面的 P{}.BLN 文件，读取自输入文件夹，写入至输出文件夹。"""
    pn_file = os.path.join(input_dir, f"pn{f1}.txt")
    bln_file = os.path.join(output_dir, f"P{f1}.BLN")
    if not os.path.exists(pn_file):
        raise FileNotFoundError(f"找不到文件: {pn_file}")

    with open(pn_file, 'r') as fin:
        b = int(fin.readline().strip())
        points = []
        for _ in range(b):
            line = fin.readline()
            parts = line.split()
            # 跳过第一列 ID，只取 X, Y
            points.append((float(parts[1]), float(parts[2])))

    with open(bln_file, 'w') as fout:
        fout.write(f"{b} 1 0\n")
        for x, y in points:
            fout.write(f"{x} {y} 0\n")

    print(f"生成 {bln_file}，点数 {b}")


def read_bln_points(filepath):
    """读取 P*.BLN 文件，返回 (x, y) 列表。"""
    with open(filepath, 'r') as f:
        n = int(f.readline().split()[0])  # 第一行第一个数字为点数
        points = []
        for _ in range(n):
            parts = f.readline().split()
            points.append((float(parts[0]), float(parts[1])))
    return points


def read_pn_points(filepath):
    """读取 PN*.TXT 文件，返回 (id, x, y) 列表。"""
    with open(filepath, 'r') as f:
        n = int(f.readline().strip())
        points = []
        for _ in range(n):
            parts = f.readline().split()
            points.append((int(parts[0]), float(parts[1]), float(parts[2])))
    return points


def find_match_index(xe1, target_x, target_y):
    """
    在 xe1 中寻找与目标坐标 (target_x, target_y) 匹配的点。
    匹配条件：坐标差在 [0, 0.06] 之间。
    返回 0‑based 索引，若未找到返回 len(xe1)（表示越界）。
    """
    nn1 = len(xe1)
    for i in range(nn1):
        dx = target_x - xe1[i][0]
        dy = target_y - xe1[i][1]
        if 0.0 <= dx <= 0.06 and 0.0 <= dy <= 0.06:
            return i
    return nn1  # 未找到


def merge_and_write_bln(fi, input_dir, output_dir):
    """
    处理相邻面 fi 和 fi+1 的数据拼接，生成 P{fi+1}.BLN。
    P{fi}.BLN 从输出文件夹读取，PN{fi+1}.TXT 从输入文件夹读取，
    P{fi+1}.BLN 写入输出文件夹。
    """
    prev_bln = os.path.join(output_dir, f"P{fi}.BLN")
    curr_pn  = os.path.join(input_dir,  f"PN{fi+1}.txt")
    next_bln = os.path.join(output_dir, f"P{fi+1}.BLN")

    if not os.path.exists(prev_bln):
        raise FileNotFoundError(f"找不到文件: {prev_bln}")
    if not os.path.exists(curr_pn):
        raise FileNotFoundError(f"找不到文件: {curr_pn}")

    # 读取前一面的边界点
    xe1 = read_bln_points(prev_bln)
    # 读取当前面的 PN 点（包含 ID）
    xe2_data = read_pn_points(curr_pn)
    nn1 = len(xe1)
    nn2 = len(xe2_data)

    # 查找 XE2 第一个点与最后一个点在 XE1 中的匹配位置
    np_idx = find_match_index(xe1, xe2_data[0][1], xe2_data[0][2])
    nq_idx = find_match_index(xe1, xe2_data[-1][1], xe2_data[-1][2])

    # 拼接点序列 (仅坐标) 与对应标志位
    pts = []
    if np_idx == nn1 and nq_idx == nn1:
        # 情况1：首尾均无匹配 —— 直接使用新面全部点
        pts = [(x, y) for _, x, y in xe2_data]
        flags = [1] + [0] * (nn2 - 2) + [1] if nn2 > 1 else [1]

    elif np_idx < nn1 and nq_idx == nn1:
        # 情况2：仅起点匹配
        pts = xe1[:np_idx+1].copy()
        pts += [(x, y) for _, x, y in xe2_data[1:]]
        total = len(pts)
        flags = [0] * total
        flags[np_idx] = 1
        flags[-1] = 1

    elif np_idx == nn1 and nq_idx < nn1:
        # 情况3：仅终点匹配
        pts = [(x, y) for _, x, y in xe2_data]
        pts += xe1[nq_idx+1:]
        total = len(pts)
        flags = [0] * total
        flags[0] = 1
        flags[nn2-1] = 1

    else:
        # 情况4：首尾均有匹配
        pts = xe1[:np_idx+1].copy()
        pts += [(x, y) for _, x, y in xe2_data[1:]]
        pts += xe1[nq_idx+1:]
        total = len(pts)
        flags = [0] * total
        flags[np_idx] = 1
        # xe2 尾点（即原 P* 文件中的匹配点）的位置
        flags[np_idx + nn2 - 1] = 1

    # 写入输出文件
    with open(next_bln, 'w') as fout:
        fout.write(f"{len(pts)} 1 0\n")
        for (x, y), flag in zip(pts, flags):
            fout.write(f"{x} {y} {flag}\n")

    print(f"生成 {next_bln}，点数 {len(pts)}")


def main():
    # ---- 交互式指定文件夹 ----
    in_dir = input("请输入输入文件夹路径（直接回车为当前目录）: ").strip()
    if not in_dir:
        in_dir = "."
    out_dir = input("请输入输出文件夹路径（直接回车与输入文件夹相同）: ").strip()
    if not out_dir:
        out_dir = in_dir

    # 自动创建输出文件夹（如果不存在）
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        print(f"已创建输出文件夹: {out_dir}")

    # 固定参数（可根据需要调整）
    f1 = 1
    f2 = 200  # 处理编号 1 到 200 的面

    # 第一步：生成第一个 BLN 文件
    generate_initial_bln(f1, in_dir, out_dir)

    # 第二步：依次处理相邻面
    for fi in range(f1, f2):
        try:
            merge_and_write_bln(fi, in_dir, out_dir)
        except FileNotFoundError as e:
            print(f"处理面 {fi} 时出错: {e}")
            break

    print("全部处理完成。")


if __name__ == "__main__":
    main()