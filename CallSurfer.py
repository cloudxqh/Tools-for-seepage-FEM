import os
import subprocess
import time
import glob
import win32com.client

# ================== 默认配置（可在此修改） ==================
# 开关：True = 使用脚本(py文件)所在目录；False = 使用下面的自定义目录
USE_SCRIPT_DIR = True

# 自定义目录（仅当 USE_SCRIPT_DIR = False 时生效）
CUSTOM_INPUT_DIR = r"D:\你的数据目录"
CUSTOM_OUTPUT_DIR = r"D:\你的输出目录"

# 脚本所在目录（绝对路径）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if USE_SCRIPT_DIR:
    INPUT_DIR = SCRIPT_DIR
    OUTPUT_DIR = SCRIPT_DIR
else:
    INPUT_DIR = os.path.abspath(CUSTOM_INPUT_DIR)
    OUTPUT_DIR = os.path.abspath(CUSTOM_OUTPUT_DIR)

SurferPath = r"D:\Golden Software\Surfer 15\Surfer.exe"
START_INDEX = 1
END_INDEX = 3
TARGET_SPACING = 5.0

# ================== 新增：可调配置（按需修改） ==================
# 以下都是"只调行为、不动主流程"的开关，默认值 = 你原来的做法。

# 中间网格命名模板。默认保持原来的 PMF{编号}.grd（不带前导零）。
# 若确认问题出在文件名位数（PMF1 vs PMF01），改成 "PMF{编号:02d}.grd" 即变 PMF01.grd
PMF_GRD_TEMPLATE = "PMF{i}.grd"

# 白化方式：True = 用 Surfer 的 GridBlank 白化（保持你原来的做法）
USE_SURFER_BLANK = True

# 白化前是否先删除已存在的输出网格（避免被占用后写入失败）
BLANK_DELETE_OUT_FIRST = True

# DXF 导出后是否校验坐标是否为数据实际坐标（只看，不改文件）
DXF_VERIFY = True

# 校验不通过时是否把 DXF 坐标整体仿射缩放到数据实际范围（应急兜底，默认关）
DXF_FIX_SCALE_IF_BAD = False

# DXF 导出缩放（实测确定，见 dxf_scale_probe3.py 的 H1 组：首顶点与 1+.dxf 逐位一致）
#   原始矩形：图形在页面上的范围（你手工在对话框里填的那组）
#   文件矩形：数据实际范围（下面按 DAT 自动算）
# 注意：在没设置 DXF_EXPORT_OPTIONS_OVERRIDE 时生效。
DXF_PAGE_LL = (1.25, 3.2412174231065)
DXF_PAGE_UR = (7.25, 7.75825768934)

# 想完全掌控导出选项就填一个完整字符串（非空时优先级最高，覆盖上面所有 DXF_* 设置）。
# 例：'ScalingSource=0,SaveScalingInfo=1,PageLLX=...,FileURY=...'
DXF_EXPORT_OPTIONS_OVERRIDE = ""

# 全部任务结束后是否退出 Surfer（调试时可设 False，保住窗口看报错）
QUIT_SURFER_AT_END = False

# 文件操作前后是否打印"存在性/大小"（排查"找不到 xxx"这类报错时很有用）
VERBOSE_FILE_CHECK = True

# ================== 插值方法（网格化算法）配置 ==================
# 直接在这里选插值方法，不用改函数。可填方法名（中文/英文都认）或直接填枚举数字。
# Surfer SrfGridAlgorithm 枚举取值：
#   1  反距离加权 (Inverse Distance)
#   2  克里金     (Kriging)              ← 本次使用
#   3  最小曲率   (Minimum Curvature)
#   4  改进谢别德 (Modified Shepard)
#   5  自然邻域   (Natural Neighbor)
#   6  最近邻     (Nearest Neighbor)
#   7  多项式回归 (Polynomial Regression)
#   8  径向基     (Radial Basis)
#   9  三角网线性插值 (Triangulation with Linear Interpolation)
INTERP_METHOD = "克里金"

# 方法名 -> 枚举号 的对照表（大小写不敏感；填数字时直接透传）
INTERP_ALGORITHMS = {
    "反距离": 1, "反距离加权": 1, "inverse": 1, "idw": 1,
    "克里金": 2, "kriging": 2,
    "最小曲率": 3, "mincurvature": 3, "minimumcurvature": 3,
    "改进谢别德": 4, "谢别德": 4, "shepard": 4, "shepards": 4,
    "自然邻域": 5, "natural": 5, "naturalneighbor": 5,
    "最近邻": 6, "nearest": 6, "nearestneighbor": 6,
    "多项式回归": 7, "回归": 7, "regression": 7,
    "径向基": 8, "radialbasis": 8, "radial": 8,
    "三角网": 9, "三角网线性插值": 9, "线性三角网": 9,
    "triangulation": 9, "linear": 9,
}

# 克里金专用：第 34 位 KrigVariogram 需要 VarioComponent 对象。
# 实测结论（vario_probe.py 在 Surfer 15.03.307 上跑出来的）：
#   · 传 None / 空元组 / 列表 / 用一个"容器"包起来 → 全部报
#     「需要一个 VarioComponent 一维数组对象」或「…数组对象」
#   · 用 app.NewVarioComponent(模型, 幂) 造出的**单个对象直接传** → 成功写出 2476924 字节网格
# 所以这里运行时用 app.NewVarioComponent(KRIG_MODEL, KRIG_POWER) 造对象。
# 说明：这两个参数的语义是从报错里反推的（参数1/2 未做 >1.17e-38 校验，参数3 起才要求正浮点），
# 实测 2 个参数能成功建对象，但**变差模型类型是否正确我没有独立验证**，
# 所以仍保留 INTERP_FALLBACK_ALGORITHM 兜底；觉得克里金结果可疑就换成 "三角网"。
KRIG_MODEL = 1        # 变差模型：1=线性（最常用）；其他取值见 Surfer 变差模型枚举
KRIG_POWER = 1.0      # 幂次（线性模型用 1.0）

# 克里金没产出网格时的兜底算法（默认 9 = 三角网线性插值）。
# 这样即使克里金变差模型还没配好，整条流水线也能先跑通；设为 0/None 可关闭兜底。
INTERP_FALLBACK_ALGORITHM = 9

# 说明：原代码写的是 hasattr(app,'srfLinearTriangle')，而本机 Surfer 15 没有这个属性，
# 会退化成 2（克里金）；现在改为由 INTERP_METHOD 显式指定，默认克里金。
# ==============================================================


# 白化输出网格格式（GridBlank 第 4 参数 OutFmt，Surfer SrfGridFormat 枚举）：
#   1=Surfer6二进制  2=Surfer6文本  3=Surfer7二进制(推荐)  4=ASCII XYZ ...
# 你原来的字面量 3 就是 Surfer 7 二进制，这里换成枚举名等价写法，更明确。
GRID_OUT_FMT = 3
# ==============================================================

# ==========================================================
# 注：本次新增的辅助函数（trace_file / read_dxf_range / rescale_dxf）
#     统一放在文件末尾的"新增辅助函数"区块，原来的函数顺序保持不变。


# 新增：智能查找文件函数（位数不固定时使用）
def find_file(directory, prefix, ext, number):
    """
    在 directory 中查找形如 prefix + 数字 + ext 的文件。
    兼容前导零：例如 prefix='PMF', ext='.DAT', number=3
    可匹配 PMF3.DAT / PMF03.DAT / PMF003.DAT
    """
    pattern = os.path.join(directory, f"{prefix}*{ext}")
    for path in glob.glob(pattern):
        name = os.path.basename(path)
        if not name.startswith(prefix):
            continue
        if not name.lower().endswith(ext.lower()):
            continue
        # 提取前缀和后缀之间的数字部分
        num_str = name[len(prefix): -len(ext)]
        # 确保是纯数字，且数值等于目标编号
        if num_str.isdigit() and int(num_str) == number:
            return path
    return None


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
        # 新增：旧网格还在就先删掉。Surfer 覆盖已存在的网格容易失败，
        # 而这一步的失败正好会表现为后面白化"找不到输入网格"。
        if BLANK_DELETE_OUT_FIRST and os.path.exists(grd_path):
            try:
                os.remove(grd_path)
                print(f"已删除旧网格：{grd_path}")
            except OSError as e:
                print(f"警告：旧网格无法删除（可能被占用）：{grd_path} -> {e}")

        xmin, xmax, ymin, ymax = get_data_range(dat_path)
        num_cols = max(2, int(round((xmax - xmin) / spacing)) + 1)
        num_rows = max(2, int(round((ymax - ymin) / spacing)) + 1)
        # 插值方法由开头的 INTERP_METHOD 决定（默认克里金），支持中文名或直接填枚举号。
        if isinstance(INTERP_METHOD, int):
            alg = INTERP_METHOD
        else:
            key = str(INTERP_METHOD).strip().lower().replace(" ", "")
            alg = INTERP_ALGORITHMS.get(key)
            if alg is None:
                raise ValueError(
                    f"INTERP_METHOD 无法识别：{INTERP_METHOD!r}，"
                    f"请用 INTERP_ALGORITHMS 里的名字或直接填枚举数字")
        print(f"插值方法：{INTERP_METHOD} (Algorithm={alg})")

        # 根因（由 surfer_api_probe.py 查到的真实签名确认）：
        #   Surfer 15 的 GridData 有 57 个参数，OutGrid 在第 50 位、OutFmt 在第 51 位，
        #   而且它返回布尔值（不返回网格对象）。
        #   原来的 app.GridData(..., OutGrid=grd_path) 只给了 16 个位置参数，
        #   第 50 位的 OutGrid 是空的，所以 Surfer 只建了内存网格、从不落盘，
        #   后面白化才报"找不到 xxx.grd"。
        # 修法：按位置把 grd_path 放到第 50 位。
        gridded = False
        try:
            gargs = [None] * 50              # 位置 1..50，未给的走 Surfer 默认值
            gargs[0] = dat_path              #  1 DataFile
            gargs[1] = 1                     #  2 xCol
            gargs[2] = 2                     #  3 yCol
            gargs[3] = 3                     #  4 zCol
            gargs[8] = num_cols              #  9 NumCols
            gargs[9] = num_rows              # 10 NumRows
            gargs[10] = xmin                 # 11 xMin
            gargs[11] = xmax                 # 12 xMax
            gargs[12] = ymin                 # 13 yMin
            gargs[13] = ymax                 # 14 yMax
            gargs[14] = alg                  # 15 Algorithm
            gargs[15] = False                # 16 ShowReport
            if alg == 2:
                # 34 KrigVariogram：克里金必须给 VarioComponent 对象（实测：单个对象即可，
                # 包成元组/列表反而会被拒）。用 NewVarioComponent(模型, 幂) 现场造。
                try:
                    gargs[33] = app.NewVarioComponent(KRIG_MODEL, KRIG_POWER)
                    print(f"  克里金变差组件：NewVarioComponent({KRIG_MODEL}, {KRIG_POWER})")
                except Exception as e:
                    print(f"  克里金变差组件创建失败：{e}")
            gargs[49] = grd_path             # 50 OutGrid ← 关键就是这一位
            ok = app.GridData(*gargs)
            gridded = True
            print(f"  GridData 返回：{ok!r}（第 50 位 OutGrid={grd_path}）")
        except Exception as e:
            print(f"  GridData 调用失败：{e}")

        # 备用：连带把 OutFmt 放在第 51 位再试一次
        if not gridded or not os.path.exists(grd_path):
            try:
                gargs2 = list(gargs) + [GRID_OUT_FMT]
                ok2 = app.GridData(*gargs2)
                gridded = True
                print(f"  GridData(含 OutFmt) 返回：{ok2!r}")
            except Exception as e:
                print(f"  GridData(含 OutFmt) 调用失败：{e}")

        # 末路备用：换 GridData2，并把 OutGrid 放到它的第 50 位、OutFmt 放第 51 位
        # （GridData2 在 34 位同样要求 VarioComponent，MiniCurvature 不受影响，
        #   所以这里只作为最后的保险，不给就跳过）
        if not gridded or not os.path.exists(grd_path):
            try:
                gargs3 = [None] * 51
                gargs3[0] = dat_path
                gargs3[1] = 1
                gargs3[2] = 2
                gargs3[3] = 3
                gargs3[8] = num_cols
                gargs3[9] = num_rows
                gargs3[10] = xmin
                gargs3[11] = xmax
                gargs3[12] = ymin
                gargs3[13] = ymax
                gargs3[14] = alg
                gargs3[15] = False
                gargs3[49] = grd_path
                gargs3[50] = GRID_OUT_FMT
                ok3 = app.GridData2(*gargs3)
                gridded = True
                print(f"  GridData2(位置版) 返回：{ok3!r}")
            except Exception as e:
                print(f"  GridData2(位置版) 调用失败：{e}")

        actual_x = (xmax - xmin) / (num_cols - 1)
        actual_y = (ymax - ymin) / (num_rows - 1)
        print(f"网格化已提交：{dat_path} -> {grd_path} (实际间距 X={actual_x:.4f}, Y={actual_y:.4f})")
        # 新增：确认 Surfer 真的写出了文件（原脚本只信返回值）
        trace_file("网格化产物", grd_path)

        # 新增：克里金失败时自动退回三角网，先让流水线跑通（克里金变差模型仍在调试中）
        if not os.path.exists(grd_path) and alg == 2 and INTERP_FALLBACK_ALGORITHM:
            print(f"克里金未产出网格，自动退回三角网(Algorithm={INTERP_FALLBACK_ALGORITHM}) 重试一次")
            gargs[14] = INTERP_FALLBACK_ALGORITHM
            gargs[33] = None
            try:
                ok_fb = app.GridData(*gargs)
                print(f"  退回后 GridData 返回：{ok_fb!r}")
            except Exception as e:
                print(f"  退回三角网也失败：{e}")
            trace_file("网格化产物", grd_path)

        if not os.path.exists(grd_path):
            raise RuntimeError(
                f"Surfer 未生成网格文件：{grd_path}\n"
                f"        第 50 位 OutGrid 已按本机真实签名传入，仍未落盘，"
                f"请把上面网格化段落里的每一行（含插值方法与报错）原样发出来。")
    except Exception as e:
        print(f"网格化失败 {dat_path}: {e}")
        raise


def blank_grid(grd_in, bln_path, grd_out, app):
    """白化：使用位置参数"""
    try:
        # 新增：先把三个路径的事实打出来。原报错是"找不到 <输出网格>"，
        # 但真正原因可能是输入网格/边界文件，或输出文件被占用，
        # 打清楚才能判断，而不是只看 Surfer 的笼统文案。
        print("白化参数：")
        trace_file("输入网格", grd_in)
        trace_file("边界文件", bln_path)
        trace_file("输出网格", grd_out)

        if not os.path.exists(grd_in):
            raise FileNotFoundError(f"输入网格不存在：{grd_in}")
        if not os.path.exists(bln_path):
            raise FileNotFoundError(f"边界文件不存在：{bln_path}")

        # 新增：输出网格若已存在，先删掉再让 Surfer 写，避免被占用/覆盖失败
        if BLANK_DELETE_OUT_FIRST and os.path.exists(grd_out):
            try:
                os.remove(grd_out)
                print(f"已删除旧输出网格：{grd_out}")
            except OSError as e:
                print(f"警告：旧输出网格无法删除（可能被占用）：{grd_out} -> {e}")

        # GridBlank 的签名（本机 Surfer 15 实测）：GridBlank(InGrid, BlankFile, OutGrid, OutFmt)
        # 第 4 个参数是输出网格格式 OutFmt（SrfGridFormat 枚举），
        # 其中 3 = srfGridFmtS7（Surfer 7 二进制），也就是你原来传的字面量 3。
        # 里/外白化由 BLN 文件里的 flag 决定（0=区域外 NoData，1=区域内 NoData），
        # 不是由这个参数控制。这里优先用枚举名，取不到再退回配置里的数字。
        out_fmt = getattr(app, 'srfGridFmtS7', GRID_OUT_FMT)
        if out_fmt is None:
            app.GridBlank(grd_in, bln_path, grd_out)
        else:
            app.GridBlank(grd_in, bln_path, grd_out, out_fmt)

        # 新增：校验白化是否真的产出文件（原报错的判据就是它）
        if not os.path.exists(grd_out):
            raise RuntimeError(
                f"GridBlank 返回后仍未找到输出网格：{grd_out}\n"
                f"        输入网格 {grd_in} 与边界 {bln_path} 都存在，"
                f"说明失败在 Surfer 内部：请检查输出目录权限、"
                f"该文件是否被其他程序（Surfer 窗口/CAD）占用。")
        print(f"白化成功：{grd_in} + {bln_path} -> {grd_out}")
        trace_file("白化产物", grd_out)
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
    try:
        # 获取数据实际坐标范围
        xmin, xmax, ymin, ymax = get_data_range(dat_path)

        plot = app.Documents.Open(srf_path)

        # 选中所有对象（等值线 + 边界，无其他）
        plot.Shapes.SelectAll()

        # 如果旧 DXF 存在则删除
        if os.path.exists(dxf_path):
            try:
                os.remove(dxf_path)
            except PermissionError:
                raise PermissionError(
                    f"DXF 文件正在被其他程序使用，请先关闭：{dxf_path}"
                )

        # 关键选项：让导出落到"输入数据的实际坐标"上（实测结论，见下）。
        # dxf_scale_probe3.py 的 H1 组用「原始矩形=(1.25,3.2412174)~(7.25,7.7587576)
        # + 文件矩形=数据范围」导出的首顶点 (1952.28989509352, 404.9987304440491)
        # 与手工导出的 1+.dxf 逐位一致，$EXTMIN/$EXTMAX 也一致，所以这组参数就是答案。
        # 反之把"原始矩形"也设成数据范围（探针 H2）导出的是页面坐标(0.9~7.3)——这就是
        # 之前一直"比例不对"的原因。
        if DXF_EXPORT_OPTIONS_OVERRIDE:
            options = DXF_EXPORT_OPTIONS_OVERRIDE
            print(f"  导出缩放：使用 DXF_EXPORT_OPTIONS_OVERRIDE 覆盖")
        else:
            p_llx, p_lly = DXF_PAGE_LL
            p_urx, p_ury = DXF_PAGE_UR
            options = (
                f"Defaults=1,"  # 重置所有选项为默认
                f"ScalingSource=1,"  # 1 = 使用应用程序提供的缩放（对应"源比例尺=图形"）
                f"SaveScalingInfo=0,"  # 不保存缩放信息（默认值）
                f"PageLLX={p_llx},"  # 原始矩形 左下角 X（图形在页面上的范围）
                f"PageLLY={p_lly},"  # 原始矩形 左下角 Y
                f"PageURX={p_urx},"  # 原始矩形 右上角 X
                f"PageURY={p_ury},"  # 原始矩形 右上角 Y
                f"FileLLX={xmin},"  # 文件矩形 左下角 X = 数据最小值
                f"FileLLY={ymin},"  # 文件矩形 左下角 Y = 数据最小值
                f"FileURX={xmax},"  # 文件矩形 右上角 X = 数据最大值
                f"FileURY={ymax}"  # 文件矩形 右上角 Y = 数据最大值
            )
            print(f"  导出缩放：原始矩形=({p_llx},{p_lly})-({p_urx},{p_ury}), "
                  f"文件矩形=({xmin},{ymin})-({xmax},{ymax})")

        plot.Export(dxf_path, True, options)  # True 表示只导出选中对象

        print(f"DXF 导出成功：{dxf_path} (坐标范围 X:{xmin}~{xmax}, Y:{ymin}~{ymax})")

        # 新增：导出后立即校验。只看不改，用数据说明"到底是不是真实坐标"。
        if DXF_VERIFY and os.path.exists(dxf_path):
            try:
                emin, emax, bbox, nvert = read_dxf_range(dxf_path)
                print(f"DXF 校验：顶点数 {nvert}")
                print(f"          $EXTMIN={emin}  $EXTMAX={emax}")
                print(f"          顶点范围={bbox}")
                if bbox:
                    tol = max(1.0, 0.01 * max(xmax - xmin, ymax - ymin))
                    ok = (xmin - tol <= bbox[0] <= xmax + tol and
                          ymin - tol <= bbox[1] <= ymax + tol and
                          xmin - tol <= bbox[2] <= xmax + tol and
                          ymin - tol <= bbox[3] <= ymax + tol)
                    # 注意：场景里还有 XYLIN 外边界底图，它的范围可能超出数据范围，
                    # 所以这里判"是否落在数据范围附近"，超出只提示、不当报错。
                    if ok:
                        print("          ✓ 坐标已是输入数据的实际坐标")
                    else:
                        print("          ✗ 顶点不在数据坐标范围内 -> 导出缩放未生效")
                        if bbox[2] < 100 and bbox[3] < 100:
                            print("            特征：坐标是页面坐标（英寸级），"
                                  "说明 ScalingSource 仍未生效")
                            print("            提示：请跑 dxf_scale_probe2.py，"
                                  "它会读出图形在页面上的实际范围"
                                  "（手工导出的『原始矩形』就是它）并实测能否导出真实坐标")
                        if DXF_FIX_SCALE_IF_BAD:
                            src, sx, sy = rescale_dxf(
                                dxf_path, dxf_path, (xmin, ymin, xmax, ymax))
                            print(f"            已仿射缩放到数据范围：{src} -> "
                                  f"({xmin},{ymin},{xmax},{ymax})，"
                                  f"比例 X x{sx:.6f} Y x{sy:.6f}")
            except Exception as e:
                print(f"DXF 校验失败（不影响导出结果）：{e}")

        plot.Close()

    except Exception as e:
        print(f"DXF 导出失败：{e}")
        raise


# ================== 以下为本次新增的辅助函数（原函数顺序未变） ==================
# 新增：打印文件是否存在及大小（排查"找不到文件"类报错）
def trace_file(tag, path):
    if not VERBOSE_FILE_CHECK:
        return
    if os.path.exists(path):
        print(f"    [{tag}] 存在 {os.path.getsize(path)} 字节 -> {path}")
    else:
        print(f"    [{tag}] 不存在 -> {path}")


# 新增：读取 DXF 的范围与顶点范围，用于校验导出坐标是否等于数据实际坐标
def read_dxf_range(dxf_path):
    """返回 (extmin, extmax, bbox, 顶点数)；解析不到的部分为 None。

    只读文本，不依赖 Surfer。extmin/extmax 取自 DXF 头的 $EXTMIN/$EXTMAX。
    """
    with open(dxf_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = [ln.rstrip('\r\n') for ln in f]

    ext = {}
    for i in range(len(lines) - 5):
        if lines[i].strip() == '9' and lines[i + 1].strip() in (
                '$EXTMIN', '$EXTMAX', '$PEXTMIN', '$PEXTMAX'):
            try:
                ext[lines[i + 1].strip()] = (float(lines[i + 3].strip()),
                                             float(lines[i + 5].strip()))
            except ValueError:
                pass

    xmin = ymin = float('inf')
    xmax = ymax = float('-inf')
    seen = 0
    pending_x = None
    for i in range(len(lines) - 1):
        code = lines[i].strip()
        if code == '10':
            try:
                pending_x = float(lines[i + 1].strip())
            except ValueError:
                pending_x = None
        elif code == '20' and pending_x is not None:
            try:
                y = float(lines[i + 1].strip())
            except ValueError:
                pending_x = None
                continue
            # 跳过 (0,0)：Surfer 导出的 POLYLINE 组头带 0,0，会污染范围判断
            if not (pending_x == 0.0 and y == 0.0):
                seen += 1
                xmin = min(xmin, pending_x); xmax = max(xmax, pending_x)
                ymin = min(ymin, y); ymax = max(ymax, y)
            pending_x = None

    bbox = None if seen == 0 else (xmin, ymin, xmax, ymax)
    return ext.get('$EXTMIN'), ext.get('$EXTMAX'), bbox, seen


# 新增：把 DXF 坐标整体仿射映射到目标范围（应急兜底，默认不启用）
def rescale_dxf(src, dst, target):
    """target=(xmin,ymin,xmax,ymax)。返回 (源范围, 比例X, 比例Y)。"""
    _, _, bbox, _ = read_dxf_range(src)
    if bbox is None:
        raise RuntimeError(f"{src}: 未读到顶点，无法缩放")
    x0, y0, x1, y1 = bbox
    tx0, ty0, tx1, ty1 = target
    if x1 == x0 or y1 == y0:
        raise RuntimeError(f"{src}: 顶点包围盒退化，无法缩放")
    sx = (tx1 - tx0) / (x1 - x0)
    sy = (ty1 - ty0) / (y1 - y0)

    with open(src, 'r', encoding='utf-8', errors='replace') as f:
        lines = [ln.rstrip('\r\n') for ln in f]

    out = []
    i = 0
    while i + 1 < len(lines):
        code = lines[i].strip()
        val = lines[i + 1].strip()
        if code in ('10', '20'):
            try:
                v = float(val)
            except ValueError:
                out.extend([lines[i], lines[i + 1]]); i += 2; continue
            v = tx0 + (v - x0) * sx if code == '10' else ty0 + (v - y0) * sy
            out.extend([lines[i], f"{v:.10f}"]); i += 2
        else:
            out.extend([lines[i], lines[i + 1]]); i += 2
    if i < len(lines):
        out.append(lines[i])

    with open(dst, 'w', encoding='ascii', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
    return bbox, sx, sy
# ================== 新增辅助函数区块结束 ==================


def main():
    print(f"USE_SCRIPT_DIR = {USE_SCRIPT_DIR}")
    print(f"输入目录：{INPUT_DIR}")
    print(f"输出目录：{OUTPUT_DIR}")
    # 新增：把关键配置打出来，便于对照本次运行实际用了哪套参数
    print(f"网格命名模板：{PMF_GRD_TEMPLATE}    Surfer 白化：{USE_SURFER_BLANK}")
    print(f"白化前删旧文件：{BLANK_DELETE_OUT_FIRST}    DXF 校验：{DXF_VERIFY}")

    try:
        app = start_surfer()
        print("Surfer 已成功启动并连接")
    except Exception as e:
        print(f"启动失败：{e}")
        return

    start = int(input(f"请输入起始编号（默认{START_INDEX}）: ") or START_INDEX)
    end = int(input(f"请输入结束编号（默认{END_INDEX}）: ") or END_INDEX)

    for i in range(start, end + 1):
        print(f"\n--- 处理第 {i} 组 ---")

        # 修改：使用 find_file 智能匹配位数不固定的文件
        # 优先查找 PMF 开头的文件（如 PMF01.DAT），找不到再尝试 PMFHJ（如 PMFHJ01.DAT）
        dat_file = find_file(INPUT_DIR, "PMF", ".DAT", i)

        # 修改：B 文件在截图里有 B1.BLN / B2.BLN，自动匹配
        blank_bln = find_file(INPUT_DIR, "B", ".BLN", i)

        # 修改：XYLIN 文件自动匹配（如 XYLIN01.BLN）
        xylin_bln = find_file(INPUT_DIR, "XYLIN", ".BLN", i)

        if dat_file is None:
            print(f"跳过：在 {INPUT_DIR} 中找不到 PMF{i}.DAT 或 PMFHJ{i}.DAT")
            continue
        if blank_bln is None:
            print(f"跳过：在 {INPUT_DIR} 中找不到 B{i}.BLN")
            continue
        if xylin_bln is None:
            print(f"跳过：在 {INPUT_DIR} 中找不到 XYLIN{i}.BLN")
            continue

        # 修改：输出文件形如 1.grd, 2.grd, 11.grd，不加前导零
        # 现在中间网格名由 PMF_GRD_TEMPLATE 控制（默认仍是原来的 PMF{i}.grd）
        pmf_grd = os.path.join(OUTPUT_DIR, PMF_GRD_TEMPLATE.format(i=i))
        final_grd = os.path.join(OUTPUT_DIR, f"{i}.grd")
        srf_file = os.path.join(OUTPUT_DIR, f"{i}.srf")
        dxf_file = os.path.join(OUTPUT_DIR, f"{i}.dxf")

        print(f"使用输入文件：{dat_file}")
        print(f"       边界：{blank_bln}")
        print(f"     外边界：{xylin_bln}")
        print(f"     中间网格：{pmf_grd}")

        grid_data(dat_file, pmf_grd, app)
        blank_grid(pmf_grd, blank_bln, final_grd, app)
        create_plot(final_grd, xylin_bln, srf_file, app)
        export_dxf(srf_file, dxf_file, app, dat_file)

    if QUIT_SURFER_AT_END:
        app.Quit()
    print("\n所有任务完成！")


if __name__ == "__main__":
    main()
