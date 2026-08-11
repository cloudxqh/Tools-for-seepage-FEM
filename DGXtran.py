import os
import math
import bisect
import ezdxf
from ezdxf.math import Vec2


def get_all_layer_names(doc):
    return [layer.dxf.name for layer in doc.layers]


def extract_vertical_lines(msp, layer_name, angle_tol=1.0):
    """
    提取竖线图层中的垂直线段，按 X 坐标合并、排序。
    返回：vx_list (排好序的X坐标列表), vy_range_list (对应每个X坐标的Y范围)
    """
    raw_segments = []

    # 处理 LINE
    for entity in msp.query('LINE'):
        if entity.dxf.layer != layer_name:
            continue
        s, e = entity.dxf.start, entity.dxf.end
        if abs(s.x - e.x) < 1e-6:
            raw_segments.append((s.x, min(s.y, e.y), max(s.y, e.y)))
        else:
            # 兼容略微倾斜的线
            angle = math.degrees(math.atan2(abs(e.x - s.x), abs(e.y - s.y)))
            if angle <= angle_tol:
                x_avg = (s.x + e.x) / 2.0
                raw_segments.append((x_avg, min(s.y, e.y), max(s.y, e.y)))

    # 处理 LWPOLYLINE
    for entity in msp.query('LWPOLYLINE'):
        if entity.dxf.layer != layer_name:
            continue
        pts = list(entity.get_points('xy'))
        if len(pts) < 2:
            continue
        if entity.closed:
            pts.append(pts[0])
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            if abs(p1[0] - p2[0]) < 1e-6:
                raw_segments.append((p1[0], min(p1[1], p2[1]), max(p1[1], p2[1])))
            else:
                angle = math.degrees(math.atan2(abs(p2[0] - p1[0]), abs(p2[1] - p1[1])))
                if angle <= angle_tol:
                    x_avg = (p1[0] + p2[0]) / 2.0
                    raw_segments.append((x_avg, min(p1[1], p2[1]), max(p1[1], p2[1])))

    if not raw_segments:
        return [], []

    # 合并相同 X 坐标的竖线
    merged_map = {}
    for x, y1, y2 in raw_segments:
        if x in merged_map:
            merged_map[x] = (min(merged_map[x][0], y1), max(merged_map[x][1], y2))
        else:
            merged_map[x] = (y1, y2)

    # 转为两个对齐的列表，便于高速二分查找
    sorted_items = sorted(merged_map.items())
    vx_list = [item[0] for item in sorted_items]
    vy_range_list = [item[1] for item in sorted_items]
    return vx_list, vy_range_list


def fast_find_intersections_for_polyline(points, vx_list, vy_range_list):
    """
    利用二分查找快速计算一条多段线所有的交点。
    返回：[(x, y), (x, y), ...] 交点列表
    """
    if len(points) < 2:
        return []

    intersections = []
    # 构建一个映射，方便从 X 坐标找到它在竖线列表中的索引
    # 因为竖线极其密集，这里我们直接使用 bisect 定位区间

    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        x1, y1 = p1[0], p1[1]
        x2, y2 = p2[0], p2[1]

        min_x = min(x1, x2)
        max_x = max(x1, x2)

        # 🚀 核心提速逻辑：利用二分查找定位竖线在 X 轴上的左右索引边界
        left_idx = bisect.bisect_left(vx_list, min_x - 1e-9)
        right_idx = bisect.bisect_right(vx_list, max_x + 1e-9)

        # 只需扫描该线段跨越的寥寥几条竖线即可（绝大部分情况下只有 1 或 2 条）
        for k in range(left_idx, right_idx):
            vx = vx_list[k]
            vy1, vy2 = vy_range_list[k]

            # 线性插值求交点 Y
            # 防止除以 0
            if abs(x2 - x1) < 1e-6:
                continue  # 水平跨越的话，不会存在交点
            t = (vx - x1) / (x2 - x1)
            if 0.0 <= t <= 1.0:
                y_int = y1 + t * (y2 - y1)
                # 检查交点是否在竖线的 Y 范围内
                if vy1 - 1e-9 <= y_int <= vy2 + 1e-9:
                    intersections.append((vx, y_int))

    return intersections


def process_terrain_entities(msp, contour_layer, vx_list, vy_range_list, output_layer):
    """遍历地形实体，计算交点并分组生成多段线"""
    # 查询 LINE 和 LWPOLYLINE
    entities = list(msp.query('LINE LWPOLYLINE'))
    total_groups = 0

    # 临时数组，存放当前正在绘制的折线的点
    current_polyline_points = []
    last_x = None

    for entity in entities:
        if entity.dxf.layer != contour_layer:
            continue

        # 提取多段线的点
        pts = []
        if entity.dxftype() == 'LINE':
            pts = [(entity.dxf.start.x, entity.dxf.start.y),
                   (entity.dxf.end.x, entity.dxf.end.y)]
        elif entity.dxftype() == 'LWPOLYLINE':
            pts = list(entity.get_points('xy'))
            if len(pts) < 2:
                continue
            if entity.closed:
                pts.append(pts[0])

        # 计算该实体上的交点
        entity_intersections = fast_find_intersections_for_polyline(pts, vx_list, vy_range_list)

        if not entity_intersections:
            continue

        # 判断是否要断开分段（如果上一个多段线的最后点和当前多段线的第一个点在 X 轴上差距过大）
        if current_polyline_points and last_x is not None:
            if abs(entity_intersections[0][0] - last_x) > 1.0:  # 阈值 1.0，发现断开就保存当前段
                if len(current_polyline_points) >= 2:
                    msp.add_lwpolyline([Vec2(p) for p in current_polyline_points], dxfattribs={'layer': output_layer})
                    total_groups += 1
                current_polyline_points = []
                last_x = None

        # 加入交点
        current_polyline_points.extend(entity_intersections)
        last_x = entity_intersections[-1][0]

    # 保存最后一段
    if len(current_polyline_points) >= 2:
        msp.add_lwpolyline([Vec2(p) for p in current_polyline_points], dxfattribs={'layer': output_layer})
        total_groups += 1

    return total_groups


def main():
    print("=== DXF 等高线-竖线交点提取 (高速优化版) ===")
    input_path = input("请输入输入 DXF 文件路径: ").strip()
    if not os.path.exists(input_path):
        print(f"❌ 文件不存在: {input_path}")
        return

    try:
        doc = ezdxf.readfile(input_path)
    except Exception as e:
        print(f"❌ 读取 DXF 失败: {e}")
        return

    msp = doc.modelspace()
    all_layers = get_all_layer_names(doc)
    print("📋 当前 DXF 图层: ", ", ".join(all_layers))

    # 1. 设置竖线图层
    while True:
        vertical_layer = input("请输入竖线所在图层名 (输入 quit 退出): ").strip()
        if vertical_layer.lower() == 'quit':
            return
        vx_list, vy_range_list = extract_vertical_lines(msp, vertical_layer)
        if vx_list:
            print(f"✅ 找到竖线 {len(vx_list)} 条。")
            break
        else:
            print(f"❌ 图层 '{vertical_layer}' 中未找到竖线。")

    # 2. 设置等高线图层
    while True:
        contour_layer = input("请输入地形线(等高线)所在图层名 (输入 quit 退出): ").strip()
        if contour_layer.lower() == 'quit':
            return
        # 快速检查图层是否存在
        terrain_entities = list(msp.query('LINE LWPOLYLINE'))
        count = sum(1 for e in terrain_entities if e.dxf.layer == contour_layer)
        if count > 0:
            print(f"✅ 在图层 '{contour_layer}' 中找到 {count} 个地形实体。")
            break
        else:
            print(f"❌ 在图层 '{contour_layer}' 中未找到任何 LINE 或 LWPOLYLINE 实体。")

    # 3. 输出设置
    output_path = input("请输入输出 DXF 文件路径: ").strip()
    if output_path and not os.path.exists(os.path.dirname(output_path)):
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        except:
            pass

    # 4. 创建输出图层
    out_layer_name = '交点线'
    try:
        doc.layers.add(out_layer_name, dxfattribs={'color': 1})
    except:
        pass

    # 5. 核心执行
    print("⏳ 正在快速计算交点并生成折线，请稍候...")
    total_groups = process_terrain_entities(msp, contour_layer, vx_list, vy_range_list, out_layer_name)

    if total_groups == 0:
        print("⚠️ 未生成任何交点线。可能原因：地形线中间没有跨越竖线、或者地形线只画在两条竖线之间。")
    else:
        print(f"🎉 共生成 {total_groups} 条独立的多段线。")

    # 6. 保存
    try:
        doc.saveas(output_path)
        print(f"✅ 成功保存至: {output_path}")
    except Exception as e:
        print(f"❌ 保存失败: {e}")


if __name__ == "__main__":
    main()