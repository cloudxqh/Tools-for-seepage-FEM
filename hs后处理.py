import math

# 修复路径：Windows 路径请用 / 或者 加 r
filename = "hs15"
input_file = fr"D:\MT3\points\{filename}.bs"  # 输入文件
output_file = fr"D:\MT3\points\{filename}_new.bs"  # 输出文件

# ================= 1. 读取文件 =================
with open(input_file, "r", encoding="utf-8") as f_in:
    lines = f_in.readlines()

# ================= 2. 解析数据 =================
blocks = []  # 用【列表】代替字典，每个元素是一个块
current_block_id = None
current_points = []
header_line = []  # 保存文件头

for idx, line in enumerate(lines):
    data = line.strip().split()
    if not data:
        continue

    # ---------- 保存文件头 ----------
    if idx == 0:
        header_line = line.strip().split()
        continue

    # ---------- 块头行 ----------
    if len(data) == 2:
        # 如果上一个块存在，先保存到列表中（不再覆盖）
        if current_block_id is not None:
            blocks.append({
                'id': current_block_id,
                'points': current_points
            })
        # 初始化新块
        current_block_id = int(data[0])
        current_points = []

    # ---------- 数据行 ----------
    elif len(data) == 4:
        p_id = int(data[0])
        x = float(data[1])
        y = float(data[2])
        z = int(data[3])  # 如果Z坐标带小数，建议改成 float(data[3])
        current_points.append([p_id, x, y, z])

# 循环结束，保存最后一个块
if current_block_id is not None:
    blocks.append({
        'id': current_block_id,
        'points': current_points
    })

for block in blocks:
    points = block['points']

    # 判断并删除相邻重复点（保留第一个）
    tolerance = 1e-6
    if points:                             # 确保不为空
        new_points = [points[0]]           # 第一个点一定保留
        last = [points[0][1], points[0][2]]  # 上一个保留点的坐标

        for pt in points[1:]:              # 从第二个点开始检查
            curr = [pt[1], pt[2]]
            distance = math.sqrt((curr[0]-last[0])**2 + (curr[1]-last[1])**2)
            if distance >= tolerance:      # 和上一个保留点距离足够大，才保留
                new_points.append(pt)
                last = curr
            else:
                # 打印被删的点
                print(f"hs{block['id']} 删除重复点，原编号: {pt[0]}")
                pass

        points[:] = new_points             # 替换原列表

    # 最后重新从1开始编号
    for i, point in enumerate(points, start=1):
        point[0] = i


    # 2. 修改 Y 值
    if len(points) < 2:
        print(f"警告：块 {block['id']} 点数不足，跳过 Y 值修正")


# ================= 3. 按块序号排序并写入文件 =================
with open(output_file, "w", encoding="utf-8") as f_out:

    # 核心修改：在写入前，按 id 从小到大对 blocks 进行排序
    sorted_blocks = sorted(blocks, key=lambda b: b['id'])
    header_line[2]=sorted_blocks[0]['id']
    header_line[3]=sorted_blocks[-1]['id']

    #print(sorted_blocks[0])
    # 先写入文件头
    f_out.write(f" {header_line[0]:<10} {header_line[1]:<12} {header_line[2]:<12} {header_line[3]}\n")

    # 再写入所有排好序的块
    for block in sorted_blocks:
        # 写入块头
        f_out.write(f" {block['id']}             {len(block['points'])}\n")

        # 写入点数据（保持格式对齐）
        for p in block['points']:
            f_out.write(f" {p[0]:<10} {p[1]:<12.4f} {p[2]:<12.4f} {p[3]}\n")

print(f"处理完成！输出文件已保存：{output_file}")
print(f"保留了原文件头，共写入 {len(blocks)} 个块 (包含重复ID的块)")