from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class Issue:
    category: str
    line: int | None
    message: str


@dataclass
class Segment:
    line_number: str
    declared_count: int | None
    header_line: int
    points: list[tuple[str, ...]]


def parse_numbers(text: str) -> list[int]:
    """Parse inputs such as 22, 23-25, or 1,3,5-8."""
    text = text.strip().replace("，", ",").replace("－", "-").replace("—", "-")
    if not text:
        raise ValueError("输入不能为空")

    numbers: set[int] = set()
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", item)
        if match:
            start, end = map(int, match.groups())
            if start > end:
                start, end = end, start
            numbers.update(range(start, end + 1))
        elif item.isdigit():
            numbers.add(int(item))
        else:
            raise ValueError(f"无法识别的范围：{item}")

    if not numbers:
        raise ValueError("没有输入有效文件号")
    return sorted(numbers)


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
    """Format X and Y/Z on every four-column point row, preserving other spacing."""
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
            match.group(1)
            + match.group(2)
            + new_x
            + match.group(4)
            + new_y
            + match.group(6)
            + "0"
            + match.group(8)
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


def check_file(path: Path) -> list[Issue]:
    text = read_text(path)
    lines = text.splitlines()
    issues: list[Issue] = []
    segments: list[Segment] = []

    if not lines:
        return [Issue("文件结构", None, "文件为空")]

    first = lines[0].strip().split()
    if len(first) != 4:
        issues.append(Issue("首行格式", 1, f"首行应为4列，实际为{len(first)}列"))
    elif not all(is_integer(value) for value in first):
        issues.append(Issue("首行格式", 1, "首行4个字段应为整数"))

    nonblank_indexes = [index for index, line in enumerate(lines) if line.strip()]
    last_data_index = nonblank_indexes[-1] if nonblank_indexes else -1

    for index in range(1, max(last_data_index, 1)):
        if not lines[index].strip():
            issues.append(Issue("空白行", index + 1, "数据中间出现空白行"))

    trailing_blank_count = max(0, len(lines) - last_data_index - 1)
    if trailing_blank_count > 1:
        issues.append(
            Issue("空白行", last_data_index + 2, f"末尾有{trailing_blank_count}行空白，只允许1行")
        )

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
                issues.append(
                    Issue("异常列数", index + 1, f"线号{line_number}下的数据应为4列，实际为{len(point_fields)}列")
                )
                index += 1
                continue

            point = tuple(point_fields)
            points.append(point)
            if not is_integer(point[0]):
                issues.append(Issue("节点序号", index + 1, f"节点序号不是整数：{point[0]}"))
            elif int(point[0]) != expected_sequence:
                issues.append(
                    Issue("节点序号", index + 1, f"线号{line_number}节点序号为{point[0]}，应为{expected_sequence}")
                )
            if not is_number(point[1]) or not is_number(point[2]):
                issues.append(Issue("节点坐标", index + 1, "X或Y/Z坐标不是有效数字"))
            if not is_number(point[3]) or Decimal(point[3]) != 0:
                issues.append(Issue("第四列", index + 1, f"线号{line_number}节点第四列为{point[3]}，应为0"))

            expected_sequence += 1
            index += 1

        if declared_count is not None and declared_count != len(points):
            issues.append(
                Issue(
                    "点数不对应",
                    header_line,
                    f"线号{line_number}线头点数为{declared_count}，实际节点数为{len(points)}",
                )
            )
        segments.append(Segment(line_number, declared_count, header_line, points))

    duplicate_groups: dict[tuple[str, int | None, tuple[tuple[str, ...], ...]], list[int]] = defaultdict(list)
    for segment in segments:
        signature = (segment.line_number, segment.declared_count, tuple(segment.points))
        duplicate_groups[signature].append(segment.header_line)

    for signature, header_lines in duplicate_groups.items():
        if len(header_lines) > 1:
            line_number, count, _ = signature
            locations = "、".join(str(line) for line in header_lines)
            issues.append(
                Issue("完全重复线段", header_lines[0], f"线号{line_number}、点数{count}及全部节点完全相同，线头行：{locations}")
            )

    return sorted(issues, key=lambda issue: (issue.line is None, issue.line or 0, issue.category))


def find_file(folder: Path, expected_name: str) -> Path | None:
    expected = expected_name.lower()
    for path in folder.iterdir():
        if path.is_file() and path.name.lower() == expected:
            return path
    return None


def main() -> None:
    folder = Path(__file__).resolve().parent
    print(f"检查文件夹：{folder}")
    print("输入示例：22  或  23-25  或  1,3,5-8")

    while True:
        try:
            numbers = parse_numbers(input("请输入要检查的HS/VS文件号范围："))
            break
        except ValueError as error:
            print(f"输入错误：{error}，请重新输入。")

    all_issues: list[tuple[str, Issue]] = []
    checked_paths: list[Path] = []
    checked_files = 0
    missing_files = 0

    print("\n开始检查：")
    for number in numbers:
        for prefix in ("hs", "vs"):
            expected_name = f"{prefix}{number}.bs"
            path = find_file(folder, expected_name)
            if path is None:
                missing_files += 1
                issue = Issue("文件缺失", None, f"未找到{expected_name}")
                all_issues.append((expected_name, issue))
                print(f"[缺失] {expected_name}")
                continue

            checked_files += 1
            checked_paths.append(path)
            issues = check_file(path)
            if not issues:
                print(f"[正常] {path.name}")
                continue

            print(f"[错误] {path.name}：共{len(issues)}项")
            for issue in issues:
                location = f"第{issue.line}行" if issue.line is not None else "文件级"
                print(f"  - [{issue.category}] {location}：{issue.message}")
                all_issues.append((path.name, issue))

    print("\n检查汇总：")
    print(f"已检查文件：{checked_files}个；缺失文件：{missing_files}个；发现问题：{len(all_issues)}项")
    if all_issues:
        counts = Counter(issue.category for _, issue in all_issues)
        for category, count in sorted(counts.items()):
            print(f"  {category}：{count}项")
    else:
        print("全部文件均符合当前HS/VS格式标准。")

    if not all_issues and checked_paths:
        print("\n开始统一保留四位小数：")
        total_points = 0
        total_changed = 0
        for path in checked_paths:
            point_count, changed_count = format_coordinates(path)
            total_points += point_count
            total_changed += changed_count
            print(f"[完成] {path.name}：节点{point_count}个，调整坐标格式{changed_count}行")

        post_format_issues: list[tuple[str, Issue]] = []
        for path in checked_paths:
            for issue in check_file(path):
                post_format_issues.append((path.name, issue))

        if post_format_issues:
            print("\n格式化后复检发现问题：")
            for name, issue in post_format_issues:
                location = f"第{issue.line}行" if issue.line is not None else "文件级"
                print(f"  - {name} [{issue.category}] {location}：{issue.message}")
        else:
            print(f"坐标处理完成：共{total_points}个节点，实际调整{total_changed}行；格式化后复检正常。")
    elif all_issues:
        print("\n存在格式错误或文件缺失，本次未修改任何坐标。")

    try:
        input("\n按回车键退出...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
