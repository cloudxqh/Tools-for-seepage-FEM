import ezdxf
from ezdxf.enums import TextEntityAlignment
import os
import re
import glob

# ========== 可配置参数 ==========
DEFAULT_BS_DIR = r"D:\DeXin\170\111\jianmo"   # 默认数据文件夹
DEFAULT_OUTPUT_DIR = r"D:\DeXin\170\out"  # 默认输出文件夹
SPACING = 10000                           # 不同编号之间的 X 方向间距（可修改）
LABEL_Y = -100                            # 组编号文本的 Y 坐标（可修改）
LABEL_HEIGHT = 100                          # 组编号文本高度（可修改）
# ================================

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


def read_bs_file(filepath, base_dir=DEFAULT_BS_DIR):
    """读取 .bs 文件，返回非空行列表，不存在则返回 None"""
    if base_dir and not os.path.isabs(filepath):
        full_path = os.path.join(base_dir, filepath)
    else:
        full_path = filepath
    if not os.path.isfile(full_path):
        return None
    with open(full_path, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines


def parse_polylines(lines):
    """从行列表中解析多段线，返回 [(线号, [(x,y), ...]), ...]"""
    polylines = []
    if not lines:
        return polylines

    data_lines = lines[1:]          # 跳过文件头
    idx = 0
    while idx < len(data_lines):
        parts = data_lines[idx].split()
        if len(parts) != 2:
            idx += 1
            continue
        try:
            line_number = int(parts[0])
            num_vertices = int(parts[1])
        except ValueError:
            idx += 1
            continue
        idx += 1
        vertices = []
        for _ in range(num_vertices):
            if idx >= len(data_lines):
                break
            v_parts = data_lines[idx].split()
            if len(v_parts) >= 3:
                x = float(v_parts[1])
                y = float(v_parts[2])
                vertices.append((x, y))
            idx += 1
        if vertices:
            polylines.append((line_number, vertices))
    return polylines


def add_polylines_to_dxf(doc, polylines, layer_name, offset_x=0):
    """
    将多段线绘制到指定图层，并整体平移 offset_x 距离。
    - 多段线 -> layer_name 图层
    - 线型比例 = 线号
    - 颜色 = (线号-1) % 100 + 1，在 1~100 之间循环
    - 每个多段线的起点处添加文本标签（线号）
    """
    if layer_name not in doc.layers:
        doc.layers.new(name=layer_name)

    msp = doc.modelspace()
    for line_number, vertices in polylines:
        if not vertices:
            continue

        # 平移顶点
        shifted_vertices = [(x + offset_x, y) for x, y in vertices]

        poly = msp.add_lwpolyline(shifted_vertices)
        poly.dxf.layer = layer_name
        poly.dxf.ltscale = float(line_number)
        color_index = ((line_number - 1) % 100) + 1
        poly.dxf.color = color_index

        # 在起点添加文本标签（平移后位置）
        text_pos = (vertices[0][0] + offset_x, vertices[0][1])
        text = msp.add_text(
            str(line_number),
            height=5
        ).set_placement(text_pos, align=TextEntityAlignment.TOP_CENTER)
        text.dxf.layer = "text"


def main():
    print("请输入要处理的编号，多个编号用空格分隔（例如：1 2 3）：")
    user_input = input(">> ").strip()

    ids = parse_range(user_input)
    if ids is None:
        # 直接回车：扫描 vs*.bs 和 hs*.bs 文件，合并提取编号
        all_ids = set()
        pattern_vs = os.path.join(DEFAULT_BS_DIR, "vs*.bs") if DEFAULT_BS_DIR else "vs*.bs"
        pattern_hs = os.path.join(DEFAULT_BS_DIR, "hs*.bs") if DEFAULT_BS_DIR else "hs*.bs"
        for pattern in (pattern_vs, pattern_hs):
            for f in glob.glob(pattern):
                basename = os.path.basename(f)
                m = re.match(r'(vs|hs)(\d+)\.bs$', basename)
                if m:
                    all_ids.add(int(m.group(2)))
        ids = sorted(all_ids)
        if not ids:
            print("未找到任何 vs*.bs 或 hs*.bs 文件，退出。")
            return
        print(f"自动匹配到编号：{ids}")
    else:
        if not ids:
            print("没有有效的编号，退出。")
            return
        print(f"将处理编号：{ids}")

    print(f"数据文件基础目录：'{DEFAULT_BS_DIR}'（空则为当前目录）")
    os.makedirs(DEFAULT_OUTPUT_DIR, exist_ok=True)
    print(f"输出文件基础目录：'{DEFAULT_OUTPUT_DIR}'")
    print(f"编号间 X 方向间距：{SPACING}")
    print(f"组编号文本位置 Y = {LABEL_Y}")

    # 创建单个 DXF 文档
    doc = ezdxf.new(dxfversion='R2010')
    msp = doc.modelspace()
    has_data = False

    # 按顺序处理每个编号，idx 用于计算偏移量
    for idx, num in enumerate(ids):
        offset = idx * SPACING   # 第一个偏移 0，第二个偏移 SPACING，依此类推

        vs_file = f"vs{num}.bs"
        hs_file = f"hs{num}.bs"

        print(f"\n正在处理编号 {num}，偏移量 X = {offset} ...")

        vs_lines = read_bs_file(vs_file)
        vs_polylines = parse_polylines(vs_lines) if vs_lines else []
        if vs_lines is None:
            print(f"  警告：文件不存在 -> {vs_file}")

        hs_lines = read_bs_file(hs_file)
        hs_polylines = parse_polylines(hs_lines) if hs_lines else []
        if hs_lines is None:
            print(f"  警告：文件不存在 -> {hs_file}")

        if not vs_polylines and not hs_polylines:
            print(f"  无有效数据，跳过编号 {num}")
            continue

        has_data = True
        if vs_polylines:
            add_polylines_to_dxf(doc, vs_polylines, "VS", offset_x=offset)
        if hs_polylines:
            add_polylines_to_dxf(doc, hs_polylines, "HS", offset_x=offset)

        # ===== 新增：在图形下方添加组编号文本 =====
        label_text = str(num)
        label_pos = (offset, LABEL_Y)
        text = msp.add_text(
            label_text,
            height=LABEL_HEIGHT
        ).set_placement(label_pos, align=TextEntityAlignment.TOP_CENTER)
        text.dxf.layer = "group_label"
        # 确保 group_label 图层存在（默认自动创建，但为保险）
        if "group_label" not in doc.layers:
            doc.layers.new(name="group_label")

    if not has_data:
        print("没有读取到任何有效数据，不生成 DXF 文件。")
        return

    # 保存合并后的 DXF
    output_dxf = os.path.join(DEFAULT_OUTPUT_DIR, f"{user_input}.dxf")
    doc.saveas(output_dxf)
    print(f"\n全部完成！合并后的 DXF 已保存至：{output_dxf}")


if __name__ == '__main__':
    main()