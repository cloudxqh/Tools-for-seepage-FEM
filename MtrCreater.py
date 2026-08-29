import os


DEFAULT_OUT_DIR = r"D:\DeXin\170\111\output"  # 默认输出文件夹


# 文件内容（保持原样，使用 \t 表示制表符）
CONTENT = """1	150	1	！	微风化千枚岩
300	150	1	！	空气
"""


def parse_range(user_input):
    """
    将用户输入的范围字符串解析为整数列表，支持 1-10 或 1,3,5 或混合。
    返回列表（可能为空）或 None（表示空输入或解析失败）。
    """
    user_input = user_input.strip()
    if not user_input:
        return None  # 空输入返回 None

    numbers = []
    parts = user_input.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-', 1)
            try:
                start = int(start)
                end = int(end)
                numbers.extend(range(start, end + 1))
            except ValueError:
                print(f"无法解析范围部分: {part}")
                return None
        else:
            try:
                numbers.append(int(part))
            except ValueError:
                print(f"无法解析编号: {part}")
                return None
    return sorted(set(numbers))


def generate_files(ids, prefix="m", ext=".mtr", out_dir=None):
    """
    根据编号列表生成文件，保存到指定目录。
    """
    if out_dir is None:
        out_dir = DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)  # 确保目录存在
    for num in ids:
        filename = f"{prefix}{num}{ext}"
        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(CONTENT)
        print(f"已生成: {filepath}")


if __name__ == "__main__":
    print("请输入要生成的编号（支持范围如 1-10，列表如 1,3,5，混合如 1,3-5,7）")
    user_input = input(">> ").strip()
    ids = parse_range(user_input)

    if ids is None:
        # 直接回车或空输入
        print("错误：未输入任何编号，程序退出。")
        exit(1)
    if not ids:
        print("错误：没有有效的编号，程序退出。")
        exit(1)

    print(f"将生成编号：{ids}")
    generate_files(ids, out_dir=DEFAULT_OUT_DIR)
    print("全部完成！")