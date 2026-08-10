"""
CAD多段线交点读取系统 (ezdxf版本)
通过读取线型比例获取手动设置的编号
支持VS和HS图层多段线处理
"""

import ezdxf
import math
from typing import List, Tuple, Dict, Optional
import os
from collections import defaultdict


class DXFIntersectionProcessor:
    def __init__(self, dxf_path: str, vs_layer: str = "VS", hs_layer: str = "HS"):
        """
        初始化DXF交点处理器

        Args:
            dxf_path: DXF文件路径
            vs_layer: VS线图层名称
            hs_layer: HS线图层名称
        """
        self.dxf_path = dxf_path
        self.doc = None
        self.model_space = None
        self.filename = None
        self.vs_layer = vs_layer
        self.hs_layer = hs_layer

    def load_dxf(self) -> bool:
        """加载DXF文件"""
        try:
            self.doc = ezdxf.readfile(self.dxf_path)
            self.model_space = self.doc.modelspace()
            base = os.path.basename(self.dxf_path)
            self.filename = os.path.splitext(base)[0]
            print(f"成功加载DXF文件: {self.dxf_path}")
            return True
        except Exception as e:
            print(f"加载DXF文件失败: {e}")
            return False

    def get_polylines_with_number(self, layer_name: str) -> Dict[int, object]:
        """
        获取指定图层中带编号的多段线
        编号通过线型比例(LTSCALE)读取

        Args:
            layer_name: 图层名称

        Returns:
            字典 {编号: 多段线对象}
        """
        numbered_polylines = {}
        unnumbered_count = 0

        try:
            # 查询轻量多段线
            for pline in self.model_space.query('LWPOLYLINE'):
                if pline.dxf.layer == layer_name:
                    # 读取线型比例作为编号
                    number = self.get_line_number(pline)
                    if number is not None:
                        if number in numbered_polylines:
                            print(f"警告: 图层'{layer_name}'中存在重复编号 {number}，将覆盖之前的多段线")
                        numbered_polylines[number] = pline
                    else:
                        unnumbered_count += 1
                        print(f"警告: 图层'{layer_name}'中存在未编号的多段线")

            # 查询传统多段线
            for pline in self.model_space.query('POLYLINE'):
                if pline.dxf.layer == layer_name:
                    number = self.get_line_number(pline)
                    if number is not None:
                        if number in numbered_polylines:
                            print(f"警告: 图层'{layer_name}'中存在重复编号 {number}，将覆盖之前的多段线")
                        numbered_polylines[number] = pline
                    else:
                        unnumbered_count += 1

            print(f"在图层'{layer_name}'中找到{len(numbered_polylines)}条已编号多段线")
            if unnumbered_count > 0:
                print(f"  (还有{unnumbered_count}条未编号的多段线)")

            return numbered_polylines

        except Exception as e:
            print(f"获取多段线失败: {e}")
            return {}

    def get_line_number(self, entity) -> Optional[int]:
        """
        从实体读取线型比例作为编号

        Args:
            entity: DXF实体对象

        Returns:
            编号(整数)，如果没有编号则返回None
        """
        try:
            # 读取线型比例
            ltscale = entity.dxf.ltscale

            # 检查是否为有效的编号
            # 编号应该是正整数
            if ltscale > 0 and abs(ltscale - round(ltscale)) < 0.001:
                return int(round(ltscale))
            else:
                return None

        except AttributeError:
            # 如果没有ltscale属性，尝试读取常量线型比例
            try:
                ltscale = entity.dxf.get('ltscale', 1.0)
                if ltscale > 0 and abs(ltscale - round(ltscale)) < 0.001:
                    return int(round(ltscale))
                else:
                    return None
            except:
                return None
        except Exception as e:
            print(f"读取线型比例失败: {e}")
            return None

    def get_all_polylines(self, layer_name: str) -> List:
        """
        获取指定图层的所有多段线（包括未编号的）

        Args:
            layer_name: 图层名称

        Returns:
            多段线对象列表
        """
        polylines = []

        try:
            # 查询轻量多段线
            for pline in self.model_space.query('LWPOLYLINE'):
                if pline.dxf.layer == layer_name:
                    polylines.append(pline)

            # 查询传统多段线
            for pline in self.model_space.query('POLYLINE'):
                if pline.dxf.layer == layer_name:
                    polylines.append(pline)

            return polylines

        except Exception as e:
            print(f"获取多段线失败: {e}")
            return []

    def get_polyline_vertices(self, polyline) -> List[Tuple[float, float]]:
        """
        获取多段线的顶点坐标

        Args:
            polyline: 多段线对象

        Returns:
            顶点坐标列表 [(x, y), ...]
        """
        vertices = []

        try:
            if polyline.dxftype() == 'LWPOLYLINE':
                # 轻量多段线 - 使用points()方法
                with polyline.points() as points:
                    for point in points:
                        vertices.append((point[0], point[1]))
            elif polyline.dxftype() == 'POLYLINE':
                # 传统多段线
                for vertex in polyline.vertices:
                    vertices.append(
                        (vertex.dxf.location.x, vertex.dxf.location.y)
                    )
        except Exception as e:
            print(f"获取顶点失败: {e}")

        return vertices

    def calculate_intersection(self, pline1_vertices: List[Tuple],
                               pline2_vertices: List[Tuple]) -> List[Tuple[float, float]]:
        """
        计算两条多段线的所有交点

        Args:
            pline1_vertices: 第一条多段线的顶点列表
            pline2_vertices: 第二条多段线的顶点列表

        Returns:
            交点坐标列表 [(x, y), ...]
        """
        intersections = []

        # 逐段计算交点
        for i in range(len(pline1_vertices) - 1):
            x1, y1 = pline1_vertices[i]
            x2, y2 = pline1_vertices[i + 1]

            for j in range(len(pline2_vertices) - 1):
                x3, y3 = pline2_vertices[j]
                x4, y4 = pline2_vertices[j + 1]

                # 使用线段相交算法
                intersection = self.line_segment_intersection(
                    x1, y1, x2, y2, x3, y3, x4, y4
                )

                if intersection:
                    intersections.append(intersection)

        # 去重
        unique_intersections = self.remove_duplicate_points(intersections)

        return unique_intersections

    def line_segment_intersection(self, x1: float, y1: float,
                                  x2: float, y2: float,
                                  x3: float, y3: float,
                                  x4: float, y4: float,
                                  tolerance: float = 1e-8) -> Optional[Tuple[float, float]]:
        """
        计算两条线段的交点（容差处理顶点交点）
        """
        denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)

        # 平行或接近平行
        if abs(denominator) < tolerance:
            return None

        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
        u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denominator

        # 扩展边界检查，允许微小溢出
        if -tolerance <= t <= 1 + tolerance and -tolerance <= u <= 1 + tolerance:
            # 钳制到 [0,1]
            t = max(0.0, min(1.0, t))
            u = max(0.0, min(1.0, u))

            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            return (x, y)

        return None

    def remove_duplicate_points(self, points: List[Tuple],
                               tolerance: float = 1e-9) -> List[Tuple]:
        """去除重复点（考虑浮点精度）"""
        unique_points = []

        for point in points:
            is_duplicate = False
            for existing_point in unique_points:
                distance = math.sqrt(
                    (point[0] - existing_point[0])**2 +
                    (point[1] - existing_point[1])**2
                )
                if distance < tolerance:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_points.append(point)

        return unique_points

    def sort_intersections_along_polyline(self,
                                         intersections: List[Tuple],
                                         polyline_vertices: List[Tuple]) -> List[Tuple]:
        """
        沿着多段线的方向排序交点

        Args:
            intersections: 交点列表
            polyline_vertices: 多段线顶点列表

        Returns:
            排序后的交点列表
        """
        if not intersections or len(intersections) <= 1:
            return intersections

        # 计算多段线的总长度和各段长度
        segment_lengths = []
        total_length = 0

        for i in range(len(polyline_vertices) - 1):
            p1 = polyline_vertices[i]
            p2 = polyline_vertices[i + 1]
            seg_length = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
            segment_lengths.append((total_length, total_length + seg_length, p1, p2))
            total_length += seg_length

        # 计算每个交点沿多段线的位置
        point_positions = []

        for point in intersections:
            # 找到交点所在的线段
            position = None

            for seg_start, seg_end, p1, p2 in segment_lengths:
                # 检查点是否在这段线段上
                if self.is_point_on_segment(point, p1, p2):
                    # 计算点在这段上的相对位置
                    dist_from_start = math.sqrt(
                        (point[0]-p1[0])**2 + (point[1]-p1[1])**2
                    )
                    position = seg_start + dist_from_start
                    break

            if position is not None:
                point_positions.append((position, point))

        # 按位置排序
        point_positions.sort(key=lambda x: x[0])

        # 返回排序后的交点
        return [point for _, point in point_positions]

    def is_point_on_segment(self, point: Tuple, seg_start: Tuple,
                           seg_end: Tuple, tolerance: float = 1e-6) -> bool:
        """检查点是否在线段上"""
        px, py = point
        x1, y1 = seg_start
        x2, y2 = seg_end

        # 计算点到线段两端点的距离
        d1 = math.sqrt((px-x1)**2 + (py-y1)**2)
        d2 = math.sqrt((px-x2)**2 + (py-y2)**2)
        d_seg = math.sqrt((x2-x1)**2 + (y2-y1)**2)

        # 如果点到两端点的距离之和等于线段长度，则点在线段上
        return abs(d1 + d2 - d_seg) < tolerance

    def process(self) -> Dict:
        """
        处理多段线交点

        Returns:
            处理结果字典
        """
        if not self.load_dxf():
            return {}

        # 获取VS线和HS线
        vs_lines = self.get_polylines_with_number(self.vs_layer)
        hs_lines = self.get_polylines_with_number(self.hs_layer)

        if not vs_lines or not hs_lines:
            print("错误：未找到足够的多段线")
            return {}

        # 获取所有目标线的顶点（用于交点计算）
        all_hs_vertices = {}
        for num, pline in hs_lines.items():
            vertices = self.get_polyline_vertices(pline)
            if vertices:
                if vertices[-1][0] < vertices[0][0]:#修正hs方向
                    vertices = vertices[::-1]
                all_hs_vertices[num] = vertices

        all_vs_vertices = {}
        for num, pline in vs_lines.items():
            vertices = self.get_polyline_vertices(pline)
            if vertices:
                if vertices[-1][1] < vertices[0][1]:#修正vs方向
                    vertices = vertices[::-1]
                all_vs_vertices[num] = vertices

        # 处理VS线与HS线的交点
        print("\n" + "="*50)
        print("处理VS线与HS线的交点")
        print("="*50)

        vs_results = {}
        for vs_num in sorted(vs_lines.keys()):
            vs_vertices = all_vs_vertices.get(vs_num)

            if not vs_vertices:
                continue

            # 计算与所有HS线的交点
            all_intersections = []
            for hs_num, hs_vertices in all_hs_vertices.items():
                intersections = self.calculate_intersection(
                    vs_vertices, hs_vertices
                )
                all_intersections.extend(intersections)

            # 去重
            all_intersections = self.remove_duplicate_points(all_intersections)

            # 沿VS线排序交点
            sorted_intersections = self.sort_intersections_along_polyline(
                all_intersections, vs_vertices
            )

            vs_results[vs_num] = {
                'type': 'VS',
                'intersections': sorted_intersections,
                'count': len(sorted_intersections)
            }

            print(f"VS线 {vs_num}: 找到{len(sorted_intersections)}个交点")

        # 处理HS线与VS线的交点
        print("\n" + "="*50)
        print("处理HS线与VS线的交点")
        print("="*50)

        hs_results = {}
        for hs_num in sorted(hs_lines.keys()):
            hs_vertices = all_hs_vertices.get(hs_num)

            if not hs_vertices:
                continue

            # 计算与所有VS线的交点
            all_intersections = []
            for vs_num, vs_vertices in all_vs_vertices.items():
                intersections = self.calculate_intersection(
                    hs_vertices, vs_vertices
                )
                all_intersections.extend(intersections)

            # 去重
            all_intersections = self.remove_duplicate_points(all_intersections)

            # 沿HS线排序交点
            sorted_intersections = self.sort_intersections_along_polyline(
                all_intersections, hs_vertices
            )

            hs_results[hs_num] = {
                'type': 'HS',
                'intersections': sorted_intersections,
                'count': len(sorted_intersections)
            }

            print(f"HS线 {hs_num}: 找到{len(sorted_intersections)}个交点")

        return {
            'vs_results': vs_results,
            'hs_results': hs_results
        }

    def save_results(self, results: Dict, output_dir: str = None):
        """
        保存结果到文本文件

        Args:
            results: 处理结果字典
            output_dir: 输出目录，默认为DXF文件所在目录
        """
        if not results:
            print("没有结果可保存")
            return

        if output_dir is None:
            output_dir = os.path.dirname(self.dxf_path)

        # 保存VS-HS交点
        vs_filepath = os.path.join(output_dir, f"vs{self.filename}.bs")
        self._save_single_result(
            results.get('vs_results', {}),
            vs_filepath
        )

        # 保存HS-VS交点
        hs_filepath = os.path.join(output_dir, f"hs{self.filename}.bs")
        self._save_single_result(
            results.get('hs_results', {}),
            hs_filepath
        )

        print(f"\n结果已保存到:")
        print(f"  - {vs_filepath}")
        print(f"  - {hs_filepath}")

    def _save_single_result(self, results: Dict, filepath: str):
        """保存单个结果文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # 按编号顺序处理每条线
                sorted_nums = sorted(results.keys())
                f.write(f"300 660 10 10\n")
                for i, line_num in enumerate(sorted_nums):
                    data = results[line_num]

                    # 第一行：线编号 交点数量
                    f.write(f"{line_num}             {data['count']}\n")

                    # 后续行：交点序号 X坐标 Y坐标 Z坐标
                    if data['count'] > 0:
                        for j, point in enumerate(data['intersections'], 1):
                            # 序号右对齐，坐标保留4位小数
                            f.write(f" {j}          {point[0]:.4f}       {point[1]:.4f}     0\n")
                    else:
                        # 没有交点时输出一行占位
                        f.write(f" 1          0.0000       0.0000     0\n")

            print(f"  已保存: {filepath}")

        except Exception as e:
            print(f"  保存失败 {filepath}: {e}")

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def export_csv(self, results: Dict, output_dir: str = None):
        """
        导出CSV格式的结果（便于Excel处理）

        Args:
            results: 处理结果字典
            output_dir: 输出目录
        """
        if not results:
            return

        if output_dir is None:
            output_dir = os.path.dirname(self.dxf_path)

        for result_type in ['vs_results', 'hs_results']:
            if result_type not in results:
                continue

            prefix = f"vs{self.filename}" if result_type == 'vs_results' else f"hs{self.filename}"
            filepath = os.path.join(output_dir, f"{prefix}交点坐标.csv")

            try:
                import csv
                with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['线编号', '线类型', '交点序号', 'X坐标', 'Y坐标'])

                    for line_num in sorted(results[result_type].keys()):
                        data = results[result_type][line_num]
                        line_type = data['type']

                        for j, point in enumerate(data['intersections'], 1):
                            writer.writerow([
                                line_num,
                                line_type,
                                j,
                                f"{point[0]:.4f}",
                                f"{point[1]:.4f}"
                            ])

                print(f"  已导出CSV: {filepath}")

            except Exception as e:
                print(f"  导出CSV失败: {e}")


def main():
    """主函数"""
    print("="*60)
    print("CAD多段线交点读取系统")
    print("通过线型比例读取手动设置的编号")
    print("="*60)

    # 输入DXF文件路径
    while True:
        dxf_path = input("\n请输入DXF文件路径: ").strip().strip('"')
        if os.path.exists(dxf_path):
            break
        print("文件不存在，请重新输入！")

    # 输入图层名称
    vs_layer = input("VS图层名称 (默认: VS): ").strip()
    if not vs_layer:
        vs_layer = "VS"

    hs_layer = input("HS图层名称 (默认: HS): ").strip()
    if not hs_layer:
        hs_layer = "HS"

    # 创建处理器
    processor = DXFIntersectionProcessor(dxf_path, vs_layer, hs_layer)

    # 处理交点
    print("\n开始处理...")
    results = processor.process()

    if results:
        # 保存结果
        print("\n保存结果...")
        processor.save_results(results)

        # 询问是否导出CSV
        export_csv = input("\n是否导出CSV格式 (y/n, 默认: n): ").strip().lower()
        if export_csv in ('y', 'yes', '是'):
            processor.export_csv(results)
            print("CSV已导出")
        else:
            print("跳过CSV导出")


        print(f"\n{dxf_path}处理完成！")
    else:
        print("\n处理失败！")


if __name__ == "__main__":
    main()