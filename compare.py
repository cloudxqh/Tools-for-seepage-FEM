import os
import filecmp
import sys

def get_pn_files(folder):
    """返回文件夹中所有 pn*.txt 文件的集合（仅文件名）"""
    if not os.path.isdir(folder):
        print(f"错误：文件夹 '{folder}' 不存在。")
        return set()
    all_files = os.listdir(folder)
    pn_files = {f for f in all_files if f.startswith("P") and f.endswith(".BLN")}
    return pn_files

def compare_files(file1, file2):
    """使用 filecmp 比较两个文件内容是否完全相同（不比较元数据）"""
    return filecmp.cmp(file1, file2, shallow=False)

def main():
    print("=== 两个文件夹中 pn*.txt 文件内容对比工具 ===")

    folder1 = input("请输入第一个文件夹路径: ").strip()
    folder2 = input("请输入第二个文件夹路径: ").strip()

    if not folder1 or not folder2:
        print("文件夹路径不能为空。")
        return

    # 获取两个文件夹中的 pn*.txt 文件集合
    files1 = get_pn_files(folder1)
    files2 = get_pn_files(folder2)

    if not files1 and not files2:
        print("两个文件夹中均未找到 pn*.txt 文件。")
        return

    # 计算共同文件和差异文件
    common = files1 & files2
    only_in_1 = files1 - files2
    only_in_2 = files2 - files1

    # 报告缺失情况
    if only_in_1:
        print(f"\n仅在第一个文件夹中存在的文件 ({len(only_in_1)} 个):")
        for f in sorted(only_in_1):
            print(f"  - {f}")
    if only_in_2:
        print(f"\n仅在第二个文件夹中存在的文件 ({len(only_in_2)} 个):")
        for f in sorted(only_in_2):
            print(f"  - {f}")

    # 对比共同文件的内容
    if common:
        print(f"\n开始对比共同文件 ({len(common)} 个)：")
        same_count = 0
        diff_count = 0
        diff_list = []

        for fname in sorted(common):
            path1 = os.path.join(folder1, fname)
            path2 = os.path.join(folder2, fname)
            if compare_files(path1, path2):
                print(f"✓ {fname} - 一致")
                same_count += 1
            else:
                print(f"✗ {fname} - 内容不同")
                diff_count += 1
                diff_list.append(fname)

        print("\n===== 汇总 =====")
        print(f"共同文件总数: {len(common)}")
        print(f"内容一致: {same_count}")
        print(f"内容不同: {diff_count}")
        if diff_list:
            print("不同的文件列表:")
            for f in diff_list:
                print(f"  - {f}")
    else:
        print("\n两个文件夹没有共同的 pn*.txt 文件。")

if __name__ == "__main__":
    main()