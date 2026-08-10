from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


DEVENV_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Microsoft Visual Studio 10.0\Common7\IDE\devenv.com"),
    Path(r"C:\Program Files\Microsoft Visual Studio 10.0\Common7\IDE\devenv.com"),
)


@dataclass(frozen=True)
class Step:
    number: int
    title: str
    project: str
    source: str
    configuration: str
    executable: str
    has_range: bool


STEPS = (
    Step(
        1,
        "生成PO",
        "1-生成poHVBtoPO-2022Liu.vfproj",
        "CompletesectionsPOtoPC - 副本(1).FOR",
        "Debug",
        "1-生成poHVBtoPO-2022Liu.exe",
        True,
    ),
    Step(
        2,
        "连接剖面并生成PC",
        "2连面CompletesectionsPOtoPC.vfproj",
        "CompletesectionsPOtoPC.FOR",
        "Release",
        "2连面CompletesectionsPOtoPC.exe",
        True,
    ),
    Step(
        3,
        "创建无材料ZJGV01.INT",
        "3-创建无材料文件Creat_ZJGV01_INT.vfproj",
        "Creat_ZJGV01_INT.F90",
        "Release",
        "3-创建无材料文件Creat_ZJGV01_INT.exe",
        True,
    ),
    Step(
        4,
        "填材料",
        "4-填材料FormMaterial(Loop).vfproj",
        "FormMaterial(Loop).FOR",
        "Debug",
        "4-填材料FormMaterial(Loop).exe",
        True,
    ),
    Step(
        5,
        "创建有材料ZJGV01.INT",
        "5-创建有材料文件PP-Creat_ZJGV01_INT.vfproj",
        "PP-Creat_ZJGV01_INT.F90",
        "Release",
        "5-创建有材料文件PP-Creat_ZJGV01_INT.exe",
        True,
    ),
    Step(
        6,
        "连接三维面",
        "6-连三维面ZNET3-F3.vfproj",
        "ZNET3-F3.FOR",
        "Release",
        "6-连三维面ZNET3-F3.exe",
        False,
    ),
    Step(
        7,
        "检查雅可比并生成OUTPUT.DAT",
        "7-检查雅克比Chack3.vfproj",
        "Chack3.for",
        "Debug",
        "7-检查雅克比Chack3.exe",
        False,
    ),
)


class WorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class Issue:
    category: str
    line: int | None
    message: str


@dataclass
class HsvsSegment:
    line_number: str
    declared_count: int | None
    header_line: int
    points: list[tuple[str, ...]]


def parse_range(text: str) -> tuple[int, int]:
    normalized = (
        text.strip()
        .replace("，", ",")
        .replace("－", "-")
        .replace("—", "-")
    )
    match = re.fullmatch(r"(\d+)\s*(?:-|,|\s+)\s*(\d+)", normalized)
    if match:
        first, last = map(int, match.groups())
    elif normalized.isdigit():
        first = last = int(normalized)
    else:
        raise ValueError("请输入类似 1-30、1 30 或 29 的连续范围")

    if first > last:
        first, last = last, first
    if first < 0:
        raise ValueError("文件号不能小于0")
    if first == last:
        raise ValueError("第6步连接三维面至少需要两个连续剖面，请输入类似29-30的范围")
    return first, last


def find_case_insensitive(folder: Path, name: str) -> Path | None:
    expected = name.casefold()
    for path in folder.iterdir():
        if path.is_file() and path.name.casefold() == expected:
            return path
    return None


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def is_integer(value: str) -> bool:
    return re.fullmatch(r"[+-]?\d+", value) is not None


def is_number(value: str) -> bool:
    try:
        return Decimal(value).is_finite()
    except InvalidOperation:
        return False


def four_decimal_places(value: str) -> str:
    rounded = Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.4f}"


def format_coordinates(path: Path) -> tuple[int, int]:
    text = read_text(path)
    source_lines = text.splitlines(keepends=True)
    output_lines: list[str] = []
    point_count = 0
    changed_count = 0
    pattern = re.compile(r"^(\s*\S+)(\s+)(\S+)(\s+)(\S+)(\s+)(\S+)(\s*)$")

    for index, raw_line in enumerate(source_lines):
        if raw_line.endswith("\r\n"):
            content, ending = raw_line[:-2], "\r\n"
        elif raw_line.endswith("\n") or raw_line.endswith("\r"):
            content, ending = raw_line[:-1], raw_line[-1]
        else:
            content, ending = raw_line, ""

        fields = content.strip().split()
        if index == 0 or len(fields) != 4:
            output_lines.append(raw_line)
            continue

        match = pattern.fullmatch(content)
        if match is None:
            raise ValueError(f"{path.name}第{index + 1}行无法保留原格式")
        new_x = four_decimal_places(fields[1])
        new_y = four_decimal_places(fields[2])
        new_content = (
            match.group(1) + match.group(2) + new_x
            + match.group(4) + new_y + match.group(6) + "0" + match.group(8)
        )
        point_count += 1
        if new_content != content:
            changed_count += 1
        output_lines.append(new_content + ending)

    new_text = "".join(output_lines)
    if new_text != text:
        temporary = path.with_name(path.name + ".formatting.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="") as file:
                file.write(new_text)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    return point_count, changed_count


def check_hsvs_file(path: Path) -> list[Issue]:
    lines = read_text(path).splitlines()
    issues: list[Issue] = []
    segments: list[HsvsSegment] = []
    if not lines:
        return [Issue("文件结构", None, "文件为空")]

    first = lines[0].strip().split()
    if len(first) != 4:
        issues.append(Issue("首行格式", 1, f"首行应为4列，实际为{len(first)}列"))
    elif not all(is_integer(value) for value in first):
        issues.append(Issue("首行格式", 1, "首行4个字段应为整数"))

    nonblank = [index for index, line in enumerate(lines) if line.strip()]
    last_data = nonblank[-1] if nonblank else -1
    for index in range(1, max(last_data, 1)):
        if not lines[index].strip():
            issues.append(Issue("空白行", index + 1, "数据中间出现空白行"))
    trailing = max(0, len(lines) - last_data - 1)
    if trailing > 1:
        issues.append(Issue("空白行", last_data + 2, f"末尾有{trailing}行空白，只允许1行"))

    index = 1
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        fields = lines[index].strip().split()
        if len(fields) != 2:
            category = "孤立节点" if len(fields) == 4 else "异常列数"
            message = "节点前没有对应的2列线头" if len(fields) == 4 else f"应为2列线头或4列节点，实际为{len(fields)}列"
            issues.append(Issue(category, index + 1, message))
            index += 1
            continue

        header_line = index + 1
        line_number = fields[0]
        declared_count: int | None = None
        if not is_integer(line_number):
            issues.append(Issue("线头格式", header_line, f"线号不是整数：{line_number}"))
        if not is_integer(fields[1]):
            issues.append(Issue("线头格式", header_line, f"点数不是整数：{fields[1]}"))
        else:
            declared_count = int(fields[1])
            if declared_count == 0:
                issues.append(Issue("零点线头", header_line, f"线号{line_number}的点数为0，应删除此线头"))
            elif declared_count < 0:
                issues.append(Issue("负点线头", header_line, f"线号{line_number}的点数为{declared_count}"))

        index += 1
        points: list[tuple[str, ...]] = []
        expected_sequence = 1
        while index < len(lines):
            if not lines[index].strip():
                index += 1
                continue
            point_fields = lines[index].strip().split()
            if len(point_fields) == 2:
                break
            if len(point_fields) != 4:
                issues.append(Issue("异常列数", index + 1, f"线号{line_number}下的数据应为4列，实际为{len(point_fields)}列"))
                index += 1
                continue

            point = tuple(point_fields)
            points.append(point)
            if not is_integer(point[0]):
                issues.append(Issue("节点序号", index + 1, f"节点序号不是整数：{point[0]}"))
            elif int(point[0]) != expected_sequence:
                issues.append(Issue("节点序号", index + 1, f"线号{line_number}节点序号为{point[0]}，应为{expected_sequence}"))
            if not is_number(point[1]) or not is_number(point[2]):
                issues.append(Issue("节点坐标", index + 1, "X或Y/Z坐标不是有效数字"))
            if not is_number(point[3]) or Decimal(point[3]) != 0:
                issues.append(Issue("第四列", index + 1, f"线号{line_number}节点第四列为{point[3]}，应为0"))
            expected_sequence += 1
            index += 1

        if declared_count is not None and declared_count != len(points):
            issues.append(Issue("点数不对应", header_line, f"线号{line_number}线头点数为{declared_count}，实际节点数为{len(points)}"))
        segments.append(HsvsSegment(line_number, declared_count, header_line, points))

    duplicate_groups: dict[tuple[str, int | None, tuple[tuple[str, ...], ...]], list[int]] = defaultdict(list)
    for segment in segments:
        duplicate_groups[(segment.line_number, segment.declared_count, tuple(segment.points))].append(segment.header_line)
    for signature, header_lines in duplicate_groups.items():
        if len(header_lines) > 1:
            locations = "、".join(str(line) for line in header_lines)
            issues.append(Issue("完全重复线段", header_lines[0], f"线号{signature[0]}、点数{signature[1]}及全部节点完全相同，线头行：{locations}"))

    return sorted(issues, key=lambda issue: (issue.line is None, issue.line or 0, issue.category))


def run_basic_check(folder: Path, first: int, last: int) -> bool:
    print("\n正在进行查错自检，基本错误将随后输出...")
    all_issues: list[tuple[str, Issue]] = []
    checked_paths: list[Path] = []

    for number in range(first, last + 1):
        for prefix in ("hs", "vs"):
            expected_name = f"{prefix}{number}.bs"
            path = find_case_insensitive(folder, expected_name)
            if path is None:
                issue = Issue("文件缺失", None, f"未找到{expected_name}")
                all_issues.append((expected_name, issue))
                print(f"[缺失] {expected_name}")
                continue
            checked_paths.append(path)
            issues = check_hsvs_file(path)
            if issues:
                print(f"[错误] {path.name}：共{len(issues)}项")
                for issue in issues:
                    location = f"第{issue.line}行" if issue.line is not None else "文件级"
                    print(f"  - [{issue.category}] {location}：{issue.message}")
                    all_issues.append((path.name, issue))
            else:
                print(f"[正常] {path.name}")

    if all_issues:
        counts = Counter(issue.category for _, issue in all_issues)
        print(f"\n查错自检未通过，共发现{len(all_issues)}项基本错误：")
        for category, count in sorted(counts.items()):
            print(f"  {category}：{count}项")
        print("已停止运行，不进入原七步程序。")
        return False

    for path in checked_paths:
        format_coordinates(path)
    post_issues: list[tuple[str, Issue]] = []
    for path in checked_paths:
        for issue in check_hsvs_file(path):
            post_issues.append((path.name, issue))
    if post_issues:
        print("\n坐标四位小数处理后复检失败：")
        for name, issue in post_issues:
            location = f"第{issue.line}行" if issue.line is not None else "文件级"
            print(f"  - {name} [{issue.category}] {location}：{issue.message}")
        print("已停止运行，不进入原七步程序。")
        return False

    print("\n无基本错误")
    return True


def find_missing_required_files(folder: Path, first: int, last: int) -> list[str]:
    required: list[str] = []
    for step in STEPS:
        required.extend((step.project, step.source))
    required.append("LNEWLOLD.txt")

    for number in range(first, last + 1):
        required.extend(
            (
                f"hs{number}.bs",
                f"vs{number}.bs",
                f"M{number}.MTR",
                f"P{number}.BLN",
            )
        )

    missing: list[str] = []
    for name in required:
        if find_case_insensitive(folder, name) is None:
            missing.append(name)
    return missing


def run_required_file_check(folder: Path, first: int, last: int) -> bool:
    print("\n正在进行七步运行程序文件自检...")
    missing = find_missing_required_files(folder, first, last)
    if not missing:
        print("七步运行所需文件齐全，继续运行。")
        return True

    print(f"发现缺少{len(missing)}个必需文件：")
    for name in missing:
        print(f"  - {name}")
    print("缺少必需文件，已停止七步自动运行程序。")
    return False


def preflight(folder: Path, first: int, last: int) -> None:
    missing = find_missing_required_files(folder, first, last)
    if missing:
        preview = missing[:30]
        suffix = "" if len(missing) <= 30 else f"\n  ……另有{len(missing) - 30}个"
        raise WorkflowError("缺少必需文件：\n  " + "\n  ".join(preview) + suffix)



def find_devenv() -> Path:
    for candidate in DEVENV_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("devenv.com")
    if found:
        return Path(found)
    raise WorkflowError("未找到Visual Studio 2010的devenv.com，无法自动编译Fortran项目")


def replace_range(source: Path, first: int, last: int) -> None:
    data = source.read_bytes()
    replacements = ((b"F1", first), (b"F2", last))
    for variable, value in replacements:
        pattern = re.compile(
            rb"(?im)^(?P<prefix>[ \t]*" + variable + rb"[ \t]*=[ \t]*)[+-]?\d+"
        )
        data, count = pattern.subn(
            lambda match, number=value: match.group("prefix") + str(number).encode("ascii"),
            data,
        )
        if count != 1:
            raise WorkflowError(f"{source.name}中的{variable.decode()}赋值出现{count}次，应为1次")
    source.write_bytes(data)


def disable_step1_final_pause(source: Path) -> bool:
    """Disable only the first, unconditional PAUSE at the end of step 1."""
    marker = b"AUTO_DISABLED_FINAL_PAUSE"
    data = source.read_bytes()
    if marker in data:
        return False

    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip(b"\r\n").strip().upper() != b"PAUSE":
            continue
        ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b"\r" if line.endswith(b"\r") else b""
        content = line[: len(line) - len(ending)] if ending else line
        indentation = content[: len(content) - len(content.lstrip(b" \t"))]
        lines[index] = indentation + b"! PAUSE  ! AUTO_DISABLED_FINAL_PAUSE" + ending
        source.write_bytes(b"".join(lines))
        return True

    raise WorkflowError(f"{source.name}中未找到主程序结束处的PAUSE")


def replace_step1_error_pauses(source: Path) -> int:
    """Replace remaining error-branch PAUSE statements so automation can exit."""
    marker = b"AUTO_REPLACED_ERROR_PAUSE"
    data = source.read_bytes()
    lines = data.splitlines(keepends=True)
    changed = 0

    for index, line in enumerate(lines):
        if line.rstrip(b"\r\n").strip().upper() != b"PAUSE":
            continue
        ending = b"\r\n" if line.endswith(b"\r\n") else b"\n" if line.endswith(b"\n") else b"\r" if line.endswith(b"\r") else b""
        content = line[: len(line) - len(ending)] if ending else line
        indentation = content[: len(content) - len(content.lstrip(b" \t"))]
        lines[index] = indentation + b"STOP 1  ! " + marker + ending
        changed += 1

    if changed:
        source.write_bytes(b"".join(lines))
    elif marker not in data:
        raise WorkflowError(f"{source.name}中未找到错误分支PAUSE")
    return changed


def decode_output(data: bytes) -> str:
    for encoding in ("mbcs", "gb18030", "utf-8"):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            pass
    return data.decode("utf-8", errors="replace")


def build_step(devenv: Path, workspace: Path, step: Step, log: list[str]) -> Path:
    project = workspace / step.project
    command = [str(devenv), str(project), "/Build", step.configuration]
    result = subprocess.run(
        command,
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = decode_output(result.stdout)
    log.append(f"\n===== 编译步骤{step.number}：{step.title} =====\n{output}")
    if result.returncode != 0:
        raise WorkflowError(f"步骤{step.number}编译失败，返回码{result.returncode}")

    executable = workspace / step.configuration / step.executable
    if not executable.is_file():
        raise WorkflowError(f"步骤{step.number}编译后未找到：{executable}")
    return executable


def run_step(executable: Path, data_folder: Path, step: Step, log: list[str]) -> None:
    result = subprocess.run(
        [str(executable)],
        cwd=data_folder,
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = decode_output(result.stdout)
    log.append(f"\n===== 运行步骤{step.number}：{step.title} =====\n{output}")

    if step.number == 1 and "9999 END OF PROGRAM" not in output:
        print("\n\n===== 第1步程序输出 =====")
        print(output.rstrip())
        print("===== 第1步程序输出结束 =====")
        raise WorkflowError("第1步未输出9999 END OF PROGRAM，已停止七步自动运行")

    lowered = output.casefold()
    failure_markers = (
        "forrtl: severe",
        "error in file",
        "traceback",
        "cannot open file",
    )
    detected = next((marker for marker in failure_markers if marker in lowered), None)
    allowed_return_codes = {0, 9999} if step.number in (6, 7) else {0}
    if result.returncode not in allowed_return_codes:
        raise WorkflowError(f"步骤{step.number}运行失败，返回码{result.returncode}")
    if detected:
        raise WorkflowError(f"步骤{step.number}运行输出中发现错误标记：{detected}")


def write_log(folder: Path, started_at: datetime, entries: list[str], result: str) -> Path:
    path = folder / f"七步自动运行_{started_at:%Y%m%d_%H%M%S}.log"
    header = f"开始时间：{started_at:%Y-%m-%d %H:%M:%S}\n结果：{result}\n"
    path.write_text(header + "".join(entries), encoding="utf-8")
    return path


def execute(first: int, last: int, build_only: bool = False) -> tuple[Path, Path | None]:
    folder = Path(__file__).resolve().parent
    started_at = datetime.now()
    log: list[str] = [f"\n运行范围：F1={first}, F2={last}\n"]
    log_path: Path | None = None

    preflight(folder, first, last)
    devenv = find_devenv()
    old_output = folder / "OUTPUT.DAT"
    old_output_mtime = old_output.stat().st_mtime_ns if old_output.exists() else None

    try:
        print(f"\n写入原源码范围：F1={first}, F2={last}", flush=True)
        for step in STEPS:
            if step.has_range:
                replace_range(folder / step.source, first, last)
                print(f"[已修改] 步骤{step.number}：{step.source}", flush=True)

        step1_source = folder / STEPS[0].source
        if disable_step1_final_pause(step1_source):
            print(f"[已处理] 步骤1结束处PAUSE已注释：{step1_source.name}", flush=True)
        else:
            print("[已确认] 步骤1结束处PAUSE已处于禁用状态", flush=True)
        error_pause_count = replace_step1_error_pauses(step1_source)
        if error_pause_count:
            print(f"[已处理] 步骤1的{error_pause_count}个错误PAUSE已改为自动退出", flush=True)
        else:
            print("[已确认] 步骤1错误分支已处于自动退出状态", flush=True)

        executables: dict[int, Path] = {}
        print("\n开始编译原目录中的7个项目：", flush=True)
        for step in STEPS:
            print(f"[{step.number}/7] 编译：{step.title} ...", end="", flush=True)
            executables[step.number] = build_step(devenv, folder, step, log)
            print("完成", flush=True)

        if build_only:
            result_text = "原源码范围已修改，7个原项目编译成功，未运行数据流程"
            log_path = write_log(folder, started_at, log, result_text)
            return log_path, None

        print("\n开始按1→7连续运行原程序：", flush=True)
        for step in STEPS:
            print(f"[{step.number}/7] 运行：{step.title} ...", end="", flush=True)
            run_step(executables[step.number], folder, step, log)
            print("完成", flush=True)

        output = folder / "OUTPUT.DAT"
        if not output.is_file():
            raise WorkflowError("七步已运行，但未生成OUTPUT.DAT")
        if old_output_mtime is not None and output.stat().st_mtime_ns == old_output_mtime:
            raise WorkflowError("OUTPUT.DAT存在，但本次运行后修改时间未变化")

        result_text = f"成功完成，F1={first}, F2={last}，输出={output}"
        log_path = write_log(folder, started_at, log, result_text)
        return log_path, output
    except Exception as error:
        log.append(f"\n===== 自动流程停止 =====\n{type(error).__name__}: {error}\n")
        log_path = write_log(folder, started_at, log, f"失败：{error}")
        if isinstance(error, WorkflowError):
            raise WorkflowError(f"{error}\n日志：{log_path}") from error
        raise WorkflowError(f"未预期错误：{error}\n日志：{log_path}") from error


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    arguments, _ = parser.parse_known_args()

    folder = Path(__file__).resolve().parent
    print(f"工作文件夹：{folder}")
    print("输入示例：1-20、1 20、1,20；第6步连接三维面至少需要两个连续剖面")
    while True:
        try:
            first, last = parse_range(input("请输入F1-F2运行范围："))
            break
        except ValueError as error:
            print(f"输入错误：{error}")

    try:
        check_passed = run_basic_check(folder, first, last)
    except Exception as error:
        print(f"\n查错自检运行失败：{error}")
        check_passed = False
    if not check_passed:
        try:
            input("\n查错自检未通过，按回车键退出...")
        except EOFError:
            pass
        return 1
    print("\n请检查：")
    print("1. 代码是否缺失；")
    print("2. HSVS文件是否已无格式错误；")
    print("3. LNEWLOLD.txt是否已修正；")
    print("4. P文件是否重整；")
    print("5. 错误节点粗筛是否修正。")
    if arguments.check_only:
        print("查错自检测试完成，未进入原七步程序。")
        return 0
    try:
        input("确认以上事项后，请按回车运行原七步程序...")
    except EOFError:
        pass
    if not run_required_file_check(folder, first, last):
        try:
            input("\n文件自检未通过，按回车键退出...")
        except EOFError:
            pass
        return 1
    print("\n执行顺序：1生成PO → 2生成PC → 3无材料文件 → 4填材料 → 5有材料文件 → 6连三维面 → 7检查雅可比")

    try:
        log_path, output = execute(first, last, arguments.build_only)
        if arguments.build_only:
            print(f"\n原源码范围已修改，7个原项目编译成功，未运行数据流程。\n日志：{log_path}")
        else:
            print(f"\n七步全部完成。\n输出：{output}\n日志：{log_path}")
            try:
                os.startfile(output)
                print("OUTPUT.DAT已自动打开。")
            except OSError as error:
                print(f"OUTPUT.DAT已生成，但自动打开失败：{error}")
        return 0
    except WorkflowError as error:
        print(f"\n自动流程失败：{error}")
        return 1
    finally:
        try:
            input("\n按回车键退出...")
        except EOFError:
            pass


if __name__ == "__main__":
    sys.exit(main())
