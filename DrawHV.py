import ezdxf
from ezdxf.enums import TextEntityAlignment
import os
import re
import glob


DEFAULT_BS_DIR = r"D:\DeXin\170\jianmo"   # 默认数据文件夹
DEFAULT_OUTPUT_DIR = r"D:\DeXin\170\out"  # 默认输出文件夹


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


def add_polylines_to_dxf(doc, polylines, layer_name):
    """
    将多段线绘制到指定图层。
    - 多段线 -> layer_name 图层
    - 线型比例 = 线号
    - 颜色 = (线号-1) % 100 + 1，在 1~100 之间循环
    """
    if layer_name not in doc.layers:
        doc.layers.new(name=layer_name)

    msp = doc.modelspace()
    for line_number, vertices in polylines:
        if not vertices:
            continue

        poly = msp.add_lwpolyline(vertices)
        poly.dxf.layer = layer_name
        poly.dxf.ltscale = float(line_number)
        # 颜色循环：线号映射到 1~100
        color_index = ((line_number - 1) % 100) + 1
        poly.dxf.color = color_index
        text=msp.add_text(
            str(line_number),
            height=5
                     ).set_placement(vertices[0], align=TextEntityAlignment.TOP_CENTER)
        text.dxf.layer = "text"


def main():
    print("请输入要处理的编号，多个编号用空格分隔（例如：1 2 3）：")
    user_input = input(">> ").strip()
    '''
    if not user_input:
        print("未输入任何编号，退出。")
        return
        '''

    ids = parse_range(user_input)
    print(ids)
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

    for num in ids:
        vs_file = f"vs{num}.bs"
        hs_file = f"hs{num}.bs"
        output_dxf = os.path.join(DEFAULT_OUTPUT_DIR, f"Surface{num}.dxf")

        print(f"\n正在处理编号 {num} ...")

        vs_lines = read_bs_file(vs_file)
        vs_polylines = parse_polylines(vs_lines) if vs_lines else []
        if vs_lines is None:
            print(f"  警告：文件不存在 -> {vs_file}")

        hs_lines = read_bs_file(hs_file)
        hs_polylines = parse_polylines(hs_lines) if hs_lines else []
        if hs_lines is None:
            print(f"  警告：文件不存在 -> {hs_file}")

        if not vs_polylines and not hs_polylines:
            print(f"  无有效数据，跳过创建 {output_dxf}")
            continue

        doc = ezdxf.new(dxfversion='R2010')
        if vs_polylines:
            add_polylines_to_dxf(doc, vs_polylines, "VS")
        if hs_polylines:
            add_polylines_to_dxf(doc, hs_polylines, "HS")

        doc.saveas(output_dxf)
        print(f"  已生成 {output_dxf}")

    print("\n全部完成！")

if __name__ == '__main__':
    main()