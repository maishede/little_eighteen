# coding='utf8'

import os

# 配置需要读取的文件类型


import os


def print_tree(start_path, prefix=""):
    """
    打印目录树结构，并且包含主文件夹名称。
    """
    # 获取所有条目并排序
    entries = sorted(os.listdir(start_path))
    # 打印顶级目录名称
    if not prefix:  # 只有在首次调用时prefix为空，此时打印顶级目录名
        print(f"{os.path.basename(start_path)}/")
    for i, entry in enumerate(entries):
        if entry.startswith("."):
            continue
        full_path = os.path.join(start_path, entry)
        is_last = i == len(entries) - 1
        if os.path.isdir(full_path):
            print(f"{prefix}├── {entry}/")
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(full_path, new_prefix)
        else:
            marker = "└── " if is_last else "├── "
            print(f"{prefix}{marker}{entry}")


INCLUDE_EXTENSIONS = ('.py', '.js', '.css', '.html')

import os

INCLUDE_EXTENSIONS = ('.py', '.js', '.css', '.html')


def read_files_with_extension(start_path):
    """
    遍历文件夹并读取指定扩展名的文件内容，然后格式化输出。
    每个文件的内容前后会添加文件名和分隔线。
    """
    content_output = []
    for root, _, files in os.walk(start_path):
        for file in sorted(files):
            if file.endswith(INCLUDE_EXTENSIONS):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                        file_content = file_content.strip()
                except Exception as e:
                    file_content = f"[无法读取文件内容: {e}]"

                # 使用"======"来分割不同的文件内容
                if file_content:
                    content_output.append(f"===== FILE: {file_path} =====\n")
                    content_output.append(file_content)
                    content_output.append("\n" + "=" * 60 + "\n")  # 添加分隔符

    print("\n".join(content_output))


base_dirname = r"D:\Code\little_eighteen"
print("以下是代码的文件结构")
print_tree(base_dirname)
print("***********" * 5)
print("\n" * 5)

backend_dirname = os.path.join(base_dirname, "app")
print("以下是后端代码")
read_files_with_extension(backend_dirname)
print("***********" * 5)
print("\n" * 5)

# static_dirname = os.path.join(base_dirname, "static")
# templates_dirname = os.path.join(base_dirname, "templates")
# print("以下是前端代码")
# read_files_with_extension(static_dirname)
# read_files_with_extension(templates_dirname)
