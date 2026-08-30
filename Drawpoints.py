import os
from ezdxf.math import Vec3
import ezdxf
from ezdxf.enums import TextEntityAlignment

# ==================== 默认配置（可修改） ====================
DEFAULT_INPUT_DIR = r"D:\DeXin\170\111\jisuan\新建文件夹"  # 默认输入目录
DEFAULT_OUTPUT_DIR = r"D:\DeXin\170\111\jisuan\新建文件夹"  # 默认输出目录
DEFAULT_INPUT_FILE = "000.txt"  # 默认输入文件名（仅当交互无输入时使用）
TEXT_HEIGHT = 2.0  # 文字高度
LAYER_NAME = "points"  # 点图层名称
TEXT_MODE = "3D"  # 文本模式："2D" 或 "3D"（启用 Z 坐标）
DXF_VERSION = "R2010"  # DXF 版本


# ===========================================================

def get_input_path():
    """交互式获取输入文件路径，支持仅输入文件名（自动拼接默认目录）。"""
    default_full = os.path.join(DEFAULT_INPUT_DIR, DEFAULT_INPUT_FILE)
    prompt = f"请输入输入点云文件路径（回车使用默认：{default_full}）："
    user_input = input(prompt).strip()
    if user_input == "":
        return default_full
    # 若输入不含路径分隔符，视为文件名，拼接默认目录
    if os.sep not in user_input and not os.path.isabs(user_input):
        return os.path.join(DEFAULT_INPUT_DIR, user_input)
    return user_input


def get_output_path(input_path):
    """
    交互式获取输出 DXF 文件路径。
    若直接回车，则根据输入文件名自动生成（同目录/输出目录，扩展名为 .dxf）。
    """
    # 根据输入文件生成默认输出文件名
    base = os.path.basename(input_path)
    name, _ = os.path.splitext(base)
    default_filename = name + ".dxf"
    default_full = os.path.join(DEFAULT_OUTPUT_DIR, default_filename)

    prompt = f"请输入输出 DXF 文件路径（回车使用默认：{default_full}）："
    user_input = input(prompt).strip()
    if user_input == "":
        return default_full
    return user_input


def parse_point_file(filepath):
    """
    解析点云文件，返回点列表，每个点为 (序号, x, y, z)。
    支持两种格式：
      1) 序号 x y z
      2) 序号 x y z 水位
    第一行为点总数，会被跳过。
    """
    points = []
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if not lines:
        return points

    # 跳过第一行（点总数）
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 4:
            continue  # 格式错误，跳过
        idx = int(parts[0])
        x = float(parts[1])
        y = float(parts[2])
        z = float(parts[3])  # 第四列始终为 Z 坐标（水位被忽略）
        points.append((idx, x, y, z))
    return points


def add_points_to_dxf(doc, points, layer_name, text_height, mode="2D"):
    """
    在 DXF 文档的模型空间中添加点文本标签。
    每个点以序号为内容，放置在 (x, y, z) 位置（Z 取决于 mode）。
    """
    if layer_name not in doc.layers:
        doc.layers.new(name=layer_name)

    msp = doc.modelspace()
    for idx, x, y, z in points:
        # 创建文本（先不设位置，后续统一设置）
        text = msp.add_text(
            str(idx),
            height=text_height,
            dxfattribs={
                'layer': layer_name,
                'color': 1,
            }
        )
        # 设置对齐方式为居中，并指定插入点
        if mode.upper() == "3D":
            # 三维模式：插入点带 Z
            text.set_placement(Vec3(x, y, z), align=TextEntityAlignment.CENTER)
        else:
            # 二维模式：Z 置 0
            text.set_placement(Vec3(x, y, 0), align=TextEntityAlignment.CENTER)


def main():
    print("===== 点云转 DXF（文本标签）=====")
    print(f"当前文本模式：{TEXT_MODE}")
    # 获取输入路径
    input_path = get_input_path()
    # 获取输出路径（自动根据输入文件名生成默认）
    output_path = get_output_path(input_path)

    # 确保输出目录存在
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    # 解析点云文件
    try:
        points = parse_point_file(input_path)
    except Exception as e:
        print(f"读取或解析文件失败：{e}")
        return

    if not points:
        print("文件为空或未解析到有效点。")
        return

    print(f"共读取到 {len(points)} 个点。")

    # 创建 DXF 文档（使用更兼容的版本 R2000）
    doc = ezdxf.new(dxfversion=DXF_VERSION)

    # 添加点文本
    add_points_to_dxf(doc, points, LAYER_NAME, TEXT_HEIGHT, TEXT_MODE)

    # 保存
    try:
        doc.saveas(output_path)
        print(f"DXF 文件已保存至：{output_path}")
    except Exception as e:
        print(f"保存 DXF 失败：{e}")


if __name__ == "__main__":
    main()