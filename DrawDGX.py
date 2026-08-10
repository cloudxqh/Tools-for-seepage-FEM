import os
import glob
import re
import ezdxf
from ezdxf import colors
from ezdxf.enums import TextEntityAlignment

def natural_sort_key(s):
    """自然排序，确保 D1, D2, ..., D10 顺序正确"""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

def main():
    print("=== 批量生成 DXF 等高线文件 ===\n")

    # 交互获取参数
    input_dir = input("请输入输入文件夹路径（存放 D*.bln 文件，默认当前目录）: ").strip() or "."
    output_dir = input("请输入输出文件夹路径（存放生成的 .dxf 文件，默认当前目录）: ").strip() or "."
    spacing_str = input("请输入每条等高线的水平间距（默认 20000）: ").strip() or "20000"

    try:
        spacing = float(spacing_str)
    except ValueError:
        print("间距输入无效，使用默认值 20000")
        spacing = 20000.0

    if not os.path.isdir(input_dir):
        print(f"错误：输入文件夹 '{input_dir}' 不存在。")
        return

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"已创建输出文件夹：{output_dir}")

    files = sorted(glob.glob(os.path.join(input_dir, "D*.bln")), key=natural_sort_key)

    if not files:
        print(f"在 '{input_dir}' 中未找到任何 D*.bln 文件。")
        return

    # 1. 创建一个新的 DXF 文档[reference:4]
    doc = ezdxf.new(dxfversion='R2010')
    msp = doc.modelspace()

    # 可选：添加一个图层来存放等高线[reference:5]
    doc.layers.add('CONTOURS', color=colors.CYAN)

    print(f"\n找到 {len(files)} 个文件，开始处理...")
    for idx, filepath in enumerate(files):
        offset = idx * spacing
        print(f"  处理: {os.path.basename(filepath)}，偏移量: {offset:.3f}")

        # 用于存储当前文件的所有点
        points = []
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 从第二行开始读取坐标
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        x = float(parts[0]) + offset
                        y = float(parts[1])
                        points.append((x, y))
                    except ValueError:
                        continue  # 跳过非数值行

        # 2. 如果成功读取到点，则在模型空间中添加一条多段线[reference:6][reference:7]
        if len(points) >= 2:
            msp.add_lwpolyline(points, dxfattribs={'layer': 'CONTOURS'})
        else:
            print(f"    警告: {os.path.basename(filepath)} 中有效点数不足，已跳过。")

    # 3. 保存 DXF 文件
    output_path = os.path.join(output_dir, 'contours.dxf')
    doc.saveas(output_path)
    print(f"\n✅ 成功生成 DXF 文件：{output_path}")
    print(f"   共处理 {len(files)} 条等高线，间距为 {spacing:.3f}。")

if __name__ == "__main__":
    main()