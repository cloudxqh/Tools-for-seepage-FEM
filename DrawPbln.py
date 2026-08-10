import ezdxf
from ezdxf.enums import TextEntityAlignment
import glob
import os
import re

def read_polyline_from_file(filepath):
    """
    读取 BLN 格式文件，返回点坐标列表。
    BLN 格式约定：
        第一行：顶点数量, 标志位（例如 "5, 1" 或 "5 1"）
        后续每行：X  Y  （两列，可能用空格或逗号分隔）
    本函数忽略第一行，读取所有后续坐标点。
    返回：
        points: [(x1,y1), (x2,y2), ...]
    """
    points = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"无法读取文件 {filepath}: {e}")
        return points

    if len(lines) < 2:
        print(f"文件 {filepath} 内容不足，跳过。")
        return points

    # 从第二行开始解析（第一行为头部）
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        # 用正则或 split 提取数值，支持逗号或空格分隔
        parts = re.split(r'[,\s]+', line)
        if len(parts) >= 2:
            try:
                x = float(parts[0])
                y = float(parts[1])
                points.append((x, y))
            except ValueError:
                print(f"忽略无效坐标行: {line} in {filepath}")
    return points

def extract_file_number(filename):
    """
    从文件名中提取第一个连续数字，例如 'boundary123.bln' -> 123
    若提取失败返回 None
    """
    match = re.search(r'(\d+)', os.path.basename(filename))
    if match:
        return int(match.group(1))
    return None

def main():
    # -------- 默认配置 ----------
    default_input_dir = "."          # 默认输入目录（当前目录）
    default_output_filename = "output.dxf"  # 默认输出文件名

    # -------- 控制台交互 ----------
    print("=== BLN 文件转 DXF 工具 ===")
    print(f"当前默认输入目录：{os.path.abspath(default_input_dir)}")
    print(f"当前默认输出文件：{os.path.abspath(default_output_filename)}")
    print()

    input_dir = input("请输入输入目录（直接回车使用默认）: ").strip()
    if not input_dir:
        input_dir = default_input_dir

    output_filename = input("请输入输出 DXF 文件名（直接回车使用默认）: ").strip()
    if not output_filename:
        output_filename = default_output_filename

    if not os.path.isdir(input_dir):
        print(f"错误：输入目录 '{input_dir}' 不存在，程序退出。")
        return

    output_dir = input_dir
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"已自动创建输出目录：{output_dir}")
        except Exception as e:
            print(f"无法创建输出目录 {output_dir}：{e}")
            return

    output_file = os.path.join(output_dir, output_filename)

    # -------- 查找所有 *.bln 文件 ----------
    pattern = os.path.join(input_dir, "*.bln")
    files = glob.glob(pattern)
    if not files:
        print(f"在目录 '{input_dir}' 中未找到任何 *.bln 文件。")
        return

    files.sort()

    # -------- 创建 DXF 并绘制多段线 ----------
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()
    count = 0

    # 顶点编号的文字高度（可自行调整）
    TEXT_HEIGHT = 3
    # 可选的偏移量，让文字不压在线条上（如 (0.5, 0.5) 表示向右上偏移）
    # 若不需要偏移，请将 OFFSET 设为 (0, 0)
    OFFSET = (0, 0)   # 改为 (0.5, 0.5) 即可产生偏移

    for idx, filename in enumerate(files):
        points = read_polyline_from_file(filename)
        if len(points) < 2:
            print(f"文件 {filename} 中的点少于2个，跳过。")
            continue

        file_num = extract_file_number(filename)
        if file_num is None:
            file_num = idx + 1
            print(f"警告：无法从文件名 {os.path.basename(filename)} 提取数字，使用索引编号 {file_num}")

        color = (file_num % 100)
        ltscale = file_num

        # 绘制多段线
        msp.add_lwpolyline(
            points,
            dxfattribs={
                'color': color,
                'ltscale': ltscale
            }
        )
        print(f"已添加 {os.path.basename(filename)}，编号 {ltscale}，颜色 {color}，包含 {len(points)} 个顶点。")

        # ----- 绘制每个顶点的顺序编号（从1开始） -----
        for i, (x, y) in enumerate(points, start=1):
            # 若需要偏移，加上偏移量
            pos_x = x + OFFSET[0]
            pos_y = y + OFFSET[1]
            # 添加文字，居中显示在坐标点（或偏移后的位置）
            text = msp.add_text(str(i), height=TEXT_HEIGHT)
            text.set_placement((pos_x, pos_y), align=TextEntityAlignment.CENTER)
            text.dxf.layer = "text"
        # ------------------------------------------------

        count += 1

    print(f"已处理 {count} 个文件，并为每个顶点生成了顺序编号。")

    # -------- 保存 DXF ----------
    try:
        doc.saveas(output_file)
        print(f"\nDXF 文件已成功保存为：{os.path.abspath(output_file)}")
    except Exception as e:
        print(f"保存 DXF 文件失败：{e}")

if __name__ == "__main__":
    main()
