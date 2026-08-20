import math
import os
import glob

# ================= 默认配置 =================
default_input_dir = r"D:\DeXin\170\HSVS"
default_output_dir = r"D:\DeXin\170\HSVS\output"
DefaultPrefix = "hs"
DefaultSuffix = "_new"
DefaultHeadline='300  190  1  190\n'

# ================= 处理单个文件的函数 =================
def process_file(input_path, output_path):
    """处理单个 .bs 文件，将结果写入 output_path"""
    with open(input_path, "r", encoding="utf-8") as f_in:
        lines = f_in.readlines()

    blocks = []
    current_block_id = None
    current_points = []
    header_line = []
    data_start = 0

    # 识别第一行是否为文件头：恰好4个整数字段
    if lines:
        first_parts = lines[0].strip().split()
        if len(first_parts) == 4 and all(p.lstrip('-').isdigit() for p in first_parts):
            header_line = first_parts
            data_start = 1

    for idx, line in enumerate(lines):
        if idx < data_start:
            continue

        data = line.strip().split()
        if not data:
            continue

        if len(data) == 2:
            if current_block_id is not None:
                blocks.append({'id': current_block_id, 'points': current_points})
            current_block_id = int(data[0])
            current_points = []

        elif len(data) == 4:
            p_id = int(data[0])
            x = float(data[1])
            y = float(data[2])
            z = int(data[3])  # 若Z为小数请改为 float(data[3])
            current_points.append([p_id, x, y, z])

    if current_block_id is not None:
        blocks.append({'id': current_block_id, 'points': current_points})

    # 处理每个块
    for block in blocks:
        points = block['points']
        tolerance = 1e-6

        if points:
            new_points = [points[0]]
            last = [points[0][1], points[0][2]]
            for pt in points[1:]:
                curr = [pt[1], pt[2]]
                distance = math.sqrt((curr[0]-last[0])**2 + (curr[1]-last[1])**2)
                if distance >= tolerance:
                    new_points.append(pt)
                    last = curr
                else:
                    print(f"文件 {os.path.basename(input_path)} 块 {block['id']} 删除重复点，原编号: {pt[0]}")
            points[:] = new_points

        # 重新编号
        for i, point in enumerate(points, start=1):
            point[0] = i

        # 预留：修改 Y 值（如需要请在此处添加逻辑）
        if len(points) < 2:
            print(f"警告：文件 {os.path.basename(input_path)} 块 {block['id']} 点数不足，跳过 Y 值修正")

    # 按块ID排序
    sorted_blocks = sorted(blocks, key=lambda b: b['id'])

    # 如果没有文件头，则使用默认文件头
    if not header_line:
        header_line = DefaultHeadline.strip().split()

    # 更新文件头中的起始块ID和结束块ID
    if sorted_blocks and len(header_line) >= 4:
        header_line[2] = str(sorted_blocks[0]['id'])
        header_line[3] = str(sorted_blocks[-1]['id'])

    # 写入输出文件
    with open(output_path, "w", encoding="utf-8") as f_out:
        if len(header_line) >= 4:
            f_out.write(f" {header_line[0]:<10} {header_line[1]:<12} {header_line[2]:<12} {header_line[3]}\n")
        else:
            f_out.write(DefaultHeadline)

        for block in sorted_blocks:
            f_out.write(f" {block['id']}             {len(block['points'])}\n")
            for p in block['points']:
                f_out.write(f" {p[0]:<10} {p[1]:<12.4f} {p[2]:<12.4f} {p[3]}\n")

# ================= 解析范围输入 =================
def parse_range(user_input):
    """将用户输入的范围字符串解析为整数列表，支持 1-10 或 1,3,5 或混合，返回列表或 None"""
    user_input = user_input.strip()
    if not user_input:
        return None

    numbers = []
    parts = user_input.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-', 1)
            try:
                start = int(start)
                end = int(end)
                numbers.extend(range(start, end + 1))
            except ValueError:
                print(f"无法解析范围部分: {part}")
                return None
        else:
            try:
                numbers.append(int(part))
            except ValueError:
                print(f"无法解析编号: {part}")
                return None
    return sorted(set(numbers))

# ================= 主程序 =================
def main():
    print("=== 批量处理 .bs 文件 ===")

    # 输入文件夹
    input_dir = input(f"请输入输入文件夹路径（默认: {default_input_dir}）：").strip()
    if not input_dir:
        input_dir = default_input_dir
    input_dir = os.path.normpath(input_dir)

    # 输出文件夹
    output_dir = input(f"请输入输出文件夹路径（默认: {default_output_dir}）：").strip()
    if not output_dir:
        output_dir = default_output_dir
    output_dir = os.path.normpath(output_dir)

    # 检查输入文件夹是否存在
    if not os.path.isdir(input_dir):
        print(f"错误：输入文件夹不存在 - {input_dir}")
        return

    # 创建输出文件夹
    os.makedirs(output_dir, exist_ok=True)

    # 文件前缀
    prefix = input(f"请输入文件名前缀（例如 hs，直接回车处理所有 .bs 文件，默认 '{DefaultPrefix}'）：").strip()
    if prefix == "":
        prefix = DefaultPrefix

    # 询问是否指定范围
    range_input = input("请输入要处理的编号范围（如 1-20 或 1,3,5，直接回车处理所有匹配文件）：").strip()
    numbers = parse_range(range_input) if range_input else None
    print(numbers)

    # 生成文件列表
    if numbers is not None:
        file_list = []
        for num in numbers:
            fname = f"{prefix}{num}.bs"
            fpath = os.path.join(input_dir, fname)
            if os.path.isfile(fpath):
                file_list.append(fpath)
            else:
                print(f"警告：文件不存在，跳过 - {fpath}")
    else:
        # 扫描所有匹配前缀的 .bs 文件
        pattern = os.path.join(input_dir, f"{prefix}*.bs")
        file_list = sorted(glob.glob(pattern), key=lambda x: int(''.join(filter(str.isdigit, os.path.basename(x)))) if any(c.isdigit() for c in os.path.basename(x)) else 0)

    if not file_list:
        print("没有找到要处理的文件。")
        return

    print(f"找到 {len(file_list)} 个文件，开始处理...")

    # 询问是否添加后缀
    add_suffix = input(f"输出文件名是否添加后缀 '{DefaultSuffix}'？(y/n，默认 y)：").strip().lower()
    if add_suffix == '' or add_suffix == 'y':
        use_suffix = True
    else:
        use_suffix = False

    # 循环处理每个文件
    for input_path in file_list:
        base_name = os.path.basename(input_path)
        stem, ext = os.path.splitext(base_name)
        if use_suffix:
            output_name = f"{stem}{DefaultSuffix}{ext}"
        else:
            output_name = base_name  # 保持原名，输出到不同文件夹
        output_path = os.path.join(output_dir, output_name)

        print(f"处理: {input_path} -> {output_path}")
        try:
            process_file(input_path, output_path)
        except Exception as e:
            print(f"处理文件 {input_path} 时出错: {e}")

    print("全部处理完成！")

if __name__ == "__main__":
    main()