import os
import subprocess
import time
import win32com.client

# ================== 默认配置（可在此修改） ==================
INPUT_DIR = r"D:\DeXin\170\111\jisuan\6反演"
OUTPUT_DIR = r"D:\DeXin\170\111\jisuan\6反演"
SurferPath = r"D:\Golden Software\Surfer 15\Surfer.exe"
START_INDEX = 1
END_INDEX = 14
TARGET_SPACING = 1.0
# ==========================================================

def get_data_range(dat_path):
    """读取 DAT 文件（三列 X Y Z），返回 X/Y 的范围"""
    x_vals, y_vals = [], []
    with open(dat_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    x = float(parts[0])
                    y = float(parts[1])
                    x_vals.append(x)
                    y_vals.append(y)
                except ValueError:
                    continue
    if not x_vals:
        raise ValueError(f"文件 {dat_path} 中未读取到有效数据")
    return min(x_vals), max(x_vals), min(y_vals), max(y_vals)

def grid_data(dat_path, grd_path, app, spacing=TARGET_SPACING):
    """网格化：线性三角网，间距≈spacing"""
    try:
        xmin, xmax, ymin, ymax = get_data_range(dat_path)
        num_cols = max(2, int(round((xmax - xmin) / spacing)) + 1)
        num_rows = max(2, int(round((ymax - ymin) / spacing)) + 1)
        alg = app.srfLinearTriangle if hasattr(app, 'srfLinearTriangle') else 5

        app.GridData(
            dat_path,
            1, 2, 3,
            None, None, None, None,
            num_cols, num_rows,
            xmin, xmax, ymin, ymax,
            alg,
            False,
            OutGrid=grd_path
        )
        actual_x = (xmax - xmin) / (num_cols - 1)
        actual_y = (ymax - ymin) / (num_rows - 1)
        print(f"网格化成功：{dat_path} -> {grd_path} (实际间距 X={actual_x:.4f}, Y={actual_y:.4f})")
    except Exception as e:
        print(f"网格化失败 {dat_path}: {e}")
        raise

def blank_grid(grd_in, bln_path, grd_out, app):
    """白化：使用位置参数"""
    try:
        app.GridBlank(grd_in, bln_path, grd_out, 3)   # 3 = 里外都白化
        print(f"白化成功：{grd_in} + {bln_path} -> {grd_out}")
    except Exception as e:
        print(f"白化失败 {grd_in}: {e}")
        raise

def create_plot(grd_path, bln_path, srf_path, app):
    """创建场景并保存（全部使用位置参数）"""
    try:
        plot = app.Documents.Add(1)
        app.Visible = True
        # 位置参数传递文件名
        plot.Shapes.AddContourMap(grd_path)
        plot.Shapes.AddBaseMap(bln_path)
        plot.SaveAs(srf_path)
        print(f"场景保存成功：{srf_path}")
        plot.Close()
    except Exception as e:
        print(f"创建场景失败 {srf_path}: {e}")
        raise

def start_surfer():
    """启动 Surfer 并返回 COM 对象"""
    try:
        app = win32com.client.Dispatch("Surfer.Application.2")
        app.Visible = False
        return app
    except:
        pass

    surf_exe = SurferPath
    if not os.path.exists(surf_exe):
        alt_path = r"C:\Program Files (x86)\Golden Software\Surfer 15\Surfer.exe"
        if os.path.exists(alt_path):
            surf_exe = alt_path
        else:
            raise FileNotFoundError("找不到 Surfer.exe，请修改 SurferPath 变量")

    subprocess.Popen([surf_exe, "/i"], shell=False,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    for _ in range(5):
        try:
            app = win32com.client.GetActiveObject("Surfer.Application.2")
            app.Visible = False
            return app
        except:
            time.sleep(1)
    raise Exception("无法连接到 Surfer，请确认 Surfer 已启动")

def export_dxf(srf_path, dxf_path, app, dat_path):
    """导出 DXF：
    1. 同时包含 Contour Map 和 XYLIN.Bln
    2. 使用 Contour Map 的实际 X/Y 坐标作为 DXF 比例尺
    """

    try:
        # 获取原始数据的实际坐标范围
        xmin, xmax, ymin, ymax = get_data_range(dat_path)

        plot = app.Documents.Open(srf_path)

        # 选中所有对象
        # Contour Map + XYLIN.Bln
        plot.Shapes.SelectAll()
        # 如果旧 DXF 存在，先删除
        if os.path.exists(dxf_path):
            try:
                os.remove(dxf_path)
                print(f"已删除旧 DXF：{dxf_path}")
            except PermissionError:
                raise PermissionError(
                    f"无法删除旧 DXF：{dxf_path}\n"
                    f"请关闭正在使用该 DXF 文件的程序后重新运行。"
                )
        # DXF 缩放参数
        #
        # ScalingSource=1
        #   使用程序提供的缩放信息
        #
        # SaveScalingInfo=1
        #   保存缩放信息
        #
        # FileLLX / FileLLY
        #   DXF 左下角实际坐标
        #
        # FileURX / FileURY
        #   DXF 右上角实际坐标
        #
        options = (
            "ScalingSource=1,"
            "SaveScalingInfo=1,"
            f"FileLLX={xmin},"
            f"FileLLY={ymin},"
            f"FileURX={xmax},"
            f"FileURY={ymax}"
        )

        # Surfer 15 COM
        # 不使用 FilterId，不使用关键字参数
        plot.Export(
            dxf_path,
            True,
            options
        )

        print(
            f"DXF 导出成功：{dxf_path} "
            f"(图形坐标范围 X={xmin}~{xmax}, Y={ymin}~{ymax})"
        )

        plot.Close()

    except Exception as e:
        print(f"DXF 导出失败 {dxf_path}: {e}")
        raise

def main():
    global INPUT_DIR, OUTPUT_DIR
    try:
        app = start_surfer()
        print("Surfer 已成功启动并连接")
    except Exception as e:
        print(f"启动失败：{e}")
        return

    print(f"默认输入目录：{INPUT_DIR}")
    print(f"默认输出目录：{OUTPUT_DIR}")
    if input("是否使用默认路径？(y/n，默认y): ").strip().lower() == 'n':
        INPUT_DIR = input("请输入输入目录（含数据文件）: ").strip()
        OUTPUT_DIR = input("请输入输出目录: ").strip()

    start = int(input(f"请输入起始编号（默认{START_INDEX}）: ") or START_INDEX)
    end = int(input(f"请输入结束编号（默认{END_INDEX}）: ") or END_INDEX)

    for i in range(start, end + 1):
        print(f"\n--- 处理第 {i} 组 ---")
        dat_file = os.path.join(INPUT_DIR, f"PMF{i}.DAT")
        pmf_grd = os.path.join(OUTPUT_DIR, f"PMF{i}.grd")
        blank_bln = os.path.join(INPUT_DIR, f"BLANK{i}.BLN")
        final_grd = os.path.join(OUTPUT_DIR, f"{i}.grd")
        xylin_bln = os.path.join(INPUT_DIR, f"XYLIN{i}.BLN")
        srf_file = os.path.join(OUTPUT_DIR, f"{i}.srf")

        if not os.path.exists(dat_file):
            print(f"跳过：{dat_file} 不存在")
            continue
        if not os.path.exists(blank_bln):
            print(f"跳过：{blank_bln} 不存在")
            continue
        if not os.path.exists(xylin_bln):
            print(f"跳过：{xylin_bln} 不存在")
            continue

        grid_data(dat_file, pmf_grd, app)
        blank_grid(pmf_grd, blank_bln, final_grd, app)
        create_plot(final_grd, xylin_bln, srf_file, app)

        dxf_file = os.path.join(OUTPUT_DIR, f"{i}.dxf")
        export_dxf(srf_file, dxf_file, app, dat_file)

    app.Quit()
    print("\n所有任务完成！")

if __name__ == "__main__":
    main()