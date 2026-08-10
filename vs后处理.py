# 修复路径：Windows 路径请用 / 或者 加 r
import math
filename = "vs15"
input_file = fr"D:\MT3\points\{filename}.bs"  # 输入文件
output_file = fr"D:\MT3\points\{filename}_new.bs"  # 输出文件


# 1. 读取文件
with open(input_file, "r", encoding="utf-8") as f_in:
    lines = f_in.readlines()

# 2. 解析数据（保留第一行文件头）
blocks = []                  # 用列表存储所有块，每个块是一个字典
current_block_id = None
current_points = []
header_line = []             # 保存文件头


for idx, line in enumerate(lines):
    data = line.strip().split()
    if not data:
        continue

    # ========== 保存文件头 ==========
    if idx == 0:
        header_line = line.strip().split()
        continue

    # ========== 块头行 ==========
    if len(data) == 2:
        block_id = int(data[0])
        # 将上一个块存入列表
        if current_block_id is not None:
            blocks.append({'id': current_block_id, 'points': current_points})
        # 开始新块
        current_block_id = block_id
        current_points = []

    # ========== 数据行 ==========
    elif len(data) == 4:
        p_id = int(data[0])
        x = float(data[1])
        y = float(data[2])
        z = int(data[3])
        current_points.append([p_id, x, y, z])


# 保存最后一个块
if current_block_id is not None:
    blocks.append({'id': current_block_id, 'points': current_points})


# 3. 去除重复点（依据 x,y 坐标距离）
tolerance = 1e-6
for block in blocks:
    pts = block['points']
    if len(pts) < 2:
        print("警告：value 长度不足2，跳过：", block['id'])
        continue

    new_pts = [pts[0]]
    last = [pts[0][1], pts[0][2]]          # 上一个保留点的 (x, y)

    for pt in pts[1:]:
        curr = [pt[1], pt[2]]
        distance = math.sqrt((curr[0]-last[0])**2 + (curr[1]-last[1])**2)
        if distance >= tolerance:          # 距离足够大，保留
            new_pts.append(pt)
            last = curr
        else:
            # 打印被删的点
            print(f"vs{block['id']} 删除重复点，原编号: {pt[0]}")

    block['points'] = new_pts             # 更新为去重后的列表


# 4. 处理最后一个点（末尾行修正）
for block in blocks:
    pts = block['points']
    if len(pts) < 2:
        print("警告：value 长度不足2，跳过：", block['id'])
        continue

    # 比较最后两行的后三个字段（x,y,z）
    if pts[-1][1:] == pts[-2][1:]:
        # 完全一样，则将最后一行的 y 改为 3000
        pts[-1][2] = 3000
    else:
        # 不一样，且最后一行的 y 不是 3000，则复制一行并将 y 改为 3000
        if pts[-1][2] != 3000:
            new_row = pts[-1].copy()
            new_row[2] = 3000
            pts.append(new_row)


# 5. 重新编号每个块内的点（从1开始）
for block in blocks:
    for i, point in enumerate(block['points'], start=1):
        point[0] = i

# 6. 写入输出文件（保留原文件头，块按 id 排序）
with open(output_file, "w", encoding="utf-8") as f_out:

    # 核心修改：在写入前，按 id 从小到大对 blocks 进行排序
    sorted_blocks = sorted(blocks, key=lambda b: b['id'])
    header_line[2] = sorted_blocks[0]['id']
    header_line[3] = sorted_blocks[-1]['id']

    # print(sorted_blocks[0])
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
print(f"保留了原文件头，共写入 {len(blocks)} 个块")


