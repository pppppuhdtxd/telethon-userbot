import os

def extract_py_files_to_txt(root_dir):
    """
    پیمایش تمام فایل‌های .py در یک دایرکتوری و زیردایرکتوری‌ها،
    خواندن محتوای آن‌ها و ذخیره در فایل‌های .txt متناظر در محل اجرای اسکریپت.
    """
    # تبدیل مسیر به مسیر استاندارد
    root_path = os.path.normpath(root_dir)

    if not os.path.isdir(root_path):
        print(f"خطا: مسیر داده شده یک دایرکتوری معتبر نیست: {root_path}")
        return

    # پیدا کردن تمام فایل‌های .py به صورت بازگشتی
    for dirpath, dirnames, filenames in os.walk(root_path):
        for file in filenames:
            if file.lower().endswith('.py'):
                py_file_path = os.path.join(dirpath, file)
                txt_file_name = f"{os.path.splitext(file)[0]}.txt"
                
                try:
                    with open(py_file_path, 'r', encoding='utf-8') as py_file:
                        content = py_file.read()
                    
                    # ذخیره محتوا در فایل txt جدید در محل اجرای اسکریپت
                    with open(txt_file_name, 'w', encoding='utf-8') as txt_file:
                        txt_file.write(content)
                    
                    print(f"محتوای '{py_file_path}' در '{txt_file_name}' ذخیره شد.")
                
                except Exception as e:
                    print(f"خطا در خواندن یا نوشتن فایل: {py_file_path}. خطا: {e}")

if __name__ == "__main__":
    target_directory = r"D:\Desktop\folder\userbot"
    extract_py_files_to_txt(target_directory)