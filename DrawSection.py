
"""
剖面绘制程序
功能：读取 NET2P*.DAT 数据文件，解析单元顶点，绘制折线并添加材料号及渗透梯度标注，输出为 DXF 文件。
新增：按材料号合并多边形（需单元闭合），使用 shapely 进行布尔并集。
支持自定义输入/输出目录、文件通配符、合并开关，交互式配置。
依赖库：ezdxf, shapely
"""

import os
import glob
import math
import sys
from pathlib import Path
import ezdxf
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union


# ========== 默认配置（可在开头修改） ==========
DEFAULT_INPUT_DIR = r"D:\DeXin\170\111\jisuan\6反演"   # 默认输入目录
DEFAULT_OUTPUT_DIR = r"D:\DeXin\170\111\jisuan\6反演\output"                       # 默认输出目录（相对路径）
DEFAULT_PATTERN = "NET2P*.DAT"                        # 默认文件匹配模式
DEFAULT_MERGE = False                                 # 默认是否合并

# ========== 交互配置 ==========
def get_config():
    """通过控制台交互获取输入输出目录、文件模式及合并开关，允许用户使用默认值或自定义"""
    print("\n===== 配置输入参数 =====")
    print(f"默认输入目录：{DEFAULT_INPUT_DIR}")
    print(f"默认输出目录：{DEFAULT_OUTPUT_DIR}")
    print(f"默认文件模式：{DEFAULT_PATTERN}")
    print(f"默认合并开关：{'启用' if DEFAULT_MERGE else '关闭'}")
    use_default = input("是否使用上述默认配置？(y/n，直接回车表示 y)：").strip().lower()
    if use_default == '' or use_default == 'y' or use_default == 'yes':
        in_dir = DEFAULT_INPUT_DIR
        out_dir = DEFAULT_OUTPUT_DIR
        pattern = DEFAULT_PATTERN
        merge = DEFAULT_MERGE
    else:
        in_dir = input("请输入输入目录路径（留空使用默认）：").strip()
        if not in_dir:
            in_dir = DEFAULT_INPUT_DIR
        out_dir = input("请输入输出目录路径（留空使用默认）：").strip()
        if not out_dir:
            out_dir = DEFAULT_OUTPUT_DIR
        pattern = input("请输入文件匹配模式（如 NET2P*.DAT，留空使用默认）：").strip()
        if not pattern:
            pattern = DEFAULT_PATTERN
        merge_input = input("是否启用合并相同材料号的多边形？(y/n，默认 n)：").strip().lower()
        merge = True if merge_input == 'y' or merge_input == 'yes' else False
    # 确保路径格式正确
    in_dir = os.path.normpath(in_dir)
    out_dir = os.path.normpath(out_dir)
    return in_dir, out_dir, pattern, merge

# ========== 辅助函数 ==========
def is_closed(coords, tol=1e-6):
    """判断多边形是否闭合（首尾距离小于阈值）"""
    if len(coords) < 3:
        return False
    dx = coords[0][0] - coords[-1][0]
    dy = coords[0][1] - coords[-1][1]
    return math.hypot(dx, dy) < tol

def draw_polyline(msp, coords, color, layer='0'):
    """绘制多段线（二维点列表）"""
    if len(coords) < 2:
        return
    points = [(x, y, 0.0) for x, y in coords]
    lwpoly = msp.add_lwpolyline(points)
    lwpoly.dxf.color = int(abs(color)) % 256
    lwpoly.dxf.layer = layer

def draw_text(msp, text, insert, height=0.5, layer='TEXT'):
    """绘制文本"""
    if not text:
        return
    obj = msp.add_text(str(text), dxfattribs={
        'height': height,
        'insert': (insert[0], insert[1], 0.0),
        'layer': layer
    })

# ========== 核心处理函数 ==========
def process_file(filepath, output_dir, merge_enabled):
    """
    处理单个 DAT 文件，生成对应的 DXF 图形
    :param filepath: 输入文件完整路径
    :param output_dir: 输出目录
    :param merge_enabled: 是否启用合并
    :return: 是否成功
    """
    print(f"\n处理文件：{filepath}")
    try:
        # 读取文件（编码兼容）
        encodings = ['gbk', 'utf-8']
        lines = None
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        if lines is None:
            raise ValueError("无法识别文件编码")

        lines = [line.strip() for line in lines if line.strip()]
        if not lines:
            print("警告：文件为空，跳过")
            return False

        idx = 0
        try:
            nez = int(lines[idx].split()[0])
        except (IndexError, ValueError):
            print("错误：第一行不是有效的单元总数")
            return False
        idx += 1

        # 收集所有单元信息
        units = []   # 每个元素: (noim1, noim2, coords_list)
        for iie in range(nez):
            if idx >= len(lines):
                print(f"警告：文件数据不足，预期 {nez} 个单元，实际只读到 {iie} 个")
                break
            parts = lines[idx].split()
            if len(parts) < 3:
                print(f"警告：第 {iie+1} 个单元头格式错误，跳过")
                idx += 1
                continue
            try:
                np_ = int(parts[0])
                noim1 = float(parts[1]) if '.' in parts[1] else int(parts[1])
                noim2 = float(parts[2]) if '.' in parts[2] else int(parts[2])
            except ValueError:
                print(f"警告：第 {iie+1} 个单元头数值解析失败，跳过")
                idx += 1
                continue
            idx += 1

            coords = []
            for i in range(np_):
                if idx >= len(lines):
                    print(f"警告：第 {iie+1} 个单元顶点数据不足，已读取 {i} 个，预期 {np_}")
                    break
                pt_parts = lines[idx].split()
                if len(pt_parts) < 2:
                    print(f"警告：第 {iie+1} 个单元第 {i+1} 个顶点格式错误，跳过")
                    idx += 1
                    continue
                try:
                    x = float(pt_parts[0])
                    y = float(pt_parts[1])
                    coords.append((x, y))
                except ValueError:
                    print(f"警告：第 {iie+1} 个单元第 {i+1} 个顶点数值解析失败，跳过")
                idx += 1
            if len(coords) >= 2:
                units.append((noim1, noim2, coords))
            else:
                print(f"警告：第 {iie+1} 个单元有效顶点少于2，忽略")

        # 创建 DXF 文档
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()

        if not merge_enabled:
            # ----- 原逻辑：逐单元绘制折线 -----
            for noim1, noim2, coords in units:
                # 计算平均中心
                avg_x = sum(p[0] for p in coords) / len(coords)
                avg_y = sum(p[1] for p in coords) / len(coords)
                xc1 = avg_x - 0.5
                xc2 = avg_y - 1.5
                yc1 = xc1
                yc2 = xc2 + 1.5

                # 绘制折线
                color = int(abs(noim1)) % 256
                draw_polyline(msp, coords, color)

                # 文本标注
                draw_text(msp, noim2, (xc1, xc2))
                draw_text(msp, noim1, (yc1, yc2))
        else:
            # ----- 合并模式 -----
            # 检查 shapely 是否可用
            if 'unary_union' not in globals():
                print("错误：shapely 未正确安装，无法使用合并功能。请安装 shapely。")
                return False

            # 按材料号分组
            groups = {}
            for noim1, noim2, coords in units:
                key = int(noim1)  # 材料号转为整数分组
                groups.setdefault(key, []).append((noim1, noim2, coords))

            # 对每个材料组进行处理
            for mat_id, unit_list in groups.items():
                # 收集所有闭合多边形
                polygons = []
                noim2_values = []
                # 处理每个单元
                for noim1, noim2, coords in unit_list:
                    noim2_values.append(noim2)
                    if is_closed(coords):
                        try:
                            poly = Polygon(coords)
                            if poly.is_valid and not poly.is_empty:
                                polygons.append(poly)
                            else:
                                # 无效多边形，仍按折线绘制
                                draw_polyline(msp, coords, mat_id)
                        except Exception:
                            # 无法构建多边形，按折线
                            draw_polyline(msp, coords, mat_id)
                    else:
                        # 不闭合，按折线
                        draw_polyline(msp, coords, mat_id)

                if not polygons:
                    # 没有有效多边形，可能已经绘制了折线，跳过标注
                    continue

                # 合并所有多边形
                try:
                    merged = unary_union(polygons)
                except Exception as e:
                    print(f"警告：材料 {mat_id} 合并失败：{e}，回退到折线绘制")
                    for _, _, coords in unit_list:
                        draw_polyline(msp, coords, mat_id)
                    continue

                # 处理合并结果
                if merged.is_empty:
                    continue

                # 计算平均渗透梯度
                avg_noim2 = sum(noim2_values) / len(noim2_values) if noim2_values else 0
                avg_noim2_str = f"{avg_noim2:.3f}".rstrip('0').rstrip('.')

                # 绘制合并后的几何体（可能是 Polygon 或 MultiPolygon）
                if isinstance(merged, Polygon):
                    geoms = [merged]
                elif isinstance(merged, MultiPolygon):
                    geoms = list(merged.geoms)
                else:
                    geoms = []

                for poly in geoms:
                    if poly.is_empty:
                        continue
                    # 取外环坐标（需闭合，但 ezdxf 自动闭合）
                    exterior_coords = list(poly.exterior.coords)
                    if len(exterior_coords) < 3:
                        continue
                    # 绘制外环
                    draw_polyline(msp, exterior_coords, mat_id)
                    # 可选：绘制内环（孔洞）作为独立多段线
                    for interior in poly.interiors:
                        interior_coords = list(interior.coords)
                        if len(interior_coords) >= 3:
                            draw_polyline(msp, interior_coords, mat_id)

                # 添加标注：在合并后所有多边形的质心处
                try:
                    centroid = merged.centroid
                    cx, cy = centroid.x, centroid.y
                    # 偏移同原逻辑
                    xc1 = cx - 0.5
                    xc2 = cy - 1.5
                    yc1 = xc1
                    yc2 = xc2 + 1.5
                    draw_text(msp, avg_noim2_str, (xc1, xc2))
                    draw_text(msp, str(mat_id), (yc1, yc2))
                except Exception as e:
                    print(f"警告：材料 {mat_id} 标注添加失败：{e}")

        # 保存 DXF
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        out_path = os.path.join(output_dir, base_name + ".dxf")
        os.makedirs(output_dir, exist_ok=True)
        doc.saveas(out_path)
        print(f"成功生成：{out_path}")
        return True

    except Exception as e:
        print(f"处理文件 {filepath} 时发生错误：{e}")
        import traceback
        traceback.print_exc()
        return False

# ========== 主程序 ==========
def main():
    in_dir, out_dir, pattern, merge = get_config()

    if not os.path.isdir(in_dir):
        print(f"错误：输入目录不存在：{in_dir}")
        sys.exit(1)

    search_path = os.path.join(in_dir, pattern)
    files = glob.glob(search_path)
    if not files:
        print(f"未找到匹配的文件：{search_path}")
        sys.exit(1)

    print(f"\n找到 {len(files)} 个文件：")
    for f in files:
        print(f"  {f}")
    print(f"合并模式：{'启用' if merge else '关闭'}")

    success_count = 0
    for f in files:
        if process_file(f, out_dir, merge):
            success_count += 1

    print(f"\n处理完成，成功 {success_count} 个，失败 {len(files)-success_count} 个。")

if __name__ == "__main__":
    main()