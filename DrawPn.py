import ezdxf
from ezdxf.enums import TextEntityAlignment
import glob
import os
import re   # 用于提取文件名中的数字

def read_polyline_from_file(filepath):
    """
    读取 pn*.txt 文件，返回点坐标列表和对应的顶点序号列表。
    文件格式：
        第一行：顶点数量（忽略）
        后续每行：序号  X坐标  Y坐标
    返回：
        points: [(x1,y1), (x2,y2), ...]
        numbers: [序号1, 序号2, ...]
    """
    points = []
    numbers = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"无法读取文件 {filepath}: {e}")
        return points, numbers   # 注意：返回两个空列表

    if not lines:
        return points, numbers

    # 从第二行开始解析（第一行是顶点数）
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                num = int(parts[0])      # 第一列为序号
                x = float(parts[1])
                y = float(parts[2])
                numbers.append(num)
                points.append((x, y))
            except ValueError:
                print(f"忽略无效行: {line} in {filepath}")
    return points, numbers   # 返回两个列表

def extract_file_number(filename):
    """
    从文件名中提取数字，例如 'pn123.txt' -> 123
    若提取失败返回 None
    """
    match = re.search(r'pn(\d+)\.txt', os.path.basename(filename))
    if match:
        return int(match.group(1))
    return None

def main():
    # -------- 默认配置 ----------
    default_input_dir = "."          # 默认输入目录（当前目录）
    default_output_filename = "output.dxf"  # 默认输出文件名

    # -------- 控制台交互 ----------
    print("=== 多段线文件转 DXF 工具 ===")
    print(f"当前默认输入目录：{os.path.abspath(default_input_dir)}")
    print(f"当前默认输出文件：{os.path.abspath(default_output_filename)}")
    print()

    # 询问输入目录
    input_dir = input("请输入输入目录（直接回车使用默认）: ").strip()
    if not input_dir:
        input_dir = default_input_dir

    # 询问输出文件
    output_filename = input("请输入输出 DXF 文件名（直接回车使用默认）: ").strip()
    if not output_filename:
        output_filename = default_output_filename

    # 检查输入目录是否存在
    if not os.path.isdir(input_dir):
        print(f"错误：输入目录 '{input_dir}' 不存在，程序退出。")
        return

    # 确保输出文件所在的目录存在
    output_dir = input_dir
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"已自动创建输出目录：{output_dir}")
        except Exception as e:
            print(f"无法创建输出目录 {output_dir}：{e}")
            return

    output_file = os.path.join(output_dir, output_filename)

    # -------- 查找所有 pn*.txt 文件 ----------
    pattern = os.path.join(input_dir, "pn*.txt")
    files = glob.glob(pattern)
    if not files:
        print(f"在目录 '{input_dir}' 中未找到任何 pn*.txt 文件。")
        return

    files.sort()  # 按文件名排序（pn1, pn2, ...）

    # -------- 创建 DXF 并绘制多段线 ----------
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()
    count = 0

    # 为每条多段线分配颜色（循环1~100）和线型比例（=文件名编号）
    for idx, filename in enumerate(files):
        # 读取数据，此处期望返回两个列表
        points, numbers = read_polyline_from_file(filename)
        if len(points) < 2:
            print(f"文件 {filename} 中的点少于2个，跳过。")
            continue

        # 提取文件名中的数字作为多段线编号
        file_num = extract_file_number(filename)
        if file_num is None:
            # 若提取失败，回退到排序索引+1
            file_num = idx + 1
            print(f"警告：无法从文件名 {os.path.basename(filename)} 提取数字，使用索引编号 {file_num}")

        # 颜色从1到100循环（idx从0开始，取模后+1）
        color = (file_num % 100)
        # 线型比例设为文件名中的数字
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

        # ----- 绘制每个顶点的编号（使用文件中的序号） -----
        # 为每个顶点添加 TEXT 实体
        for num, (x, y) in zip(numbers, points):
            # 将序号转为字符串
            text = str(num)
            # 在顶点位置创建文字（直接放在坐标上）
            text = msp.add_text(
                str(num),
                height=5
            ).set_placement((x, y), align=TextEntityAlignment.TOP_CENTER)
            text.dxf.layer = "text"
        # ------------------------------------------------

        count += 1

    print(f"已处理 {count} 个文件，并绘制了所有顶点编号。")

    # -------- 保存 DXF ----------
    try:
        doc.saveas(output_file)
        print(f"\nDXF 文件已成功保存为：{os.path.abspath(output_file)}")
    except Exception as e:
        print(f"保存 DXF 文件失败：{e}")

if __name__ == "__main__":
    main()