import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import logging
from pathlib import Path
from src.ai_engine import AIEngine

# 修正 Windows 高 DPI 模糊問題
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

class ComicTranslatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🎨 AI 漫畫翻譯工具")
        self.root.geometry("820x900")
        self.root.resizable(False, False)
        # self.root.minsize(860, 750)

        # 設定 logging
        self.setup_logging()

        # 變數
        self.api_key_var = tk.StringVar()
        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.is_processing = False

        # 建立介面
        self.create_widgets()

        # 載入上次的設定（需在 create_widgets 之後，因為需要存取 text widgets）
        self.load_config()

    def setup_logging(self):
        """設定 logging"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    def load_config(self):
        """載入上次的設定"""
        config_file = Path("gui_config.txt")
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if len(lines) >= 2:
                        self.input_dir_var.set(lines[0].strip())
                        self.output_dir_var.set(lines[1].strip())
            except:
                pass

        # 載入翻譯配置
        self.load_translation_config()

    def save_config(self):
        """儲存設定"""
        try:
            with open("gui_config.txt", 'w', encoding='utf-8') as f:
                f.write(f"{self.input_dir_var.get()}\n")
                f.write(f"{self.output_dir_var.get()}\n")
        except:
            pass

    def create_widgets(self):
        """建立介面元件"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 標題
        title_label = ttk.Label(main_frame, text="🎨 AI 漫畫翻譯工具", font=('Arial', 18, 'bold'), anchor='center')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10), sticky=(tk.W, tk.E))

        # API Key 區域
        api_frame = ttk.LabelFrame(main_frame, text="API 設定", padding="5 3 0 3")
        api_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))

        ttk.Label(api_frame, text="Gemini API Key:", width=13).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, width=48, show="*")
        api_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=10)

        help_btn = ttk.Button(api_frame, text="❓ 如何取得", command=self.show_api_help, width=10)
        help_btn.grid(row=0, column=2)

        # 資料夾選擇區域
        folder_frame = ttk.LabelFrame(main_frame, text="資料夾設定", padding="3")
        folder_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))

        # 輸入資料夾
        ttk.Label(folder_frame, text="輸入資料夾:", width=12).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        ttk.Entry(folder_frame, textvariable=self.input_dir_var, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=10, pady=(0, 10))
        ttk.Button(folder_frame, text="瀏覽...", command=self.browse_input_dir, width=10).grid(row=0, column=2, pady=(0, 10))

        # 輸出資料夾
        ttk.Label(folder_frame, text="輸出資料夾:", width=12).grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(folder_frame, textvariable=self.output_dir_var, width=50).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=10)
        ttk.Button(folder_frame, text="瀏覽...", command=self.browse_output_dir, width=10).grid(row=1, column=2)

        # 自訂翻譯設定區域
        custom_frame = ttk.LabelFrame(main_frame, text="自訂翻譯設定 (選填)", padding="5")
        custom_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))

        # 全域設定 - 人名對照（套用到所有圖片）
        global_label = ttk.Label(custom_frame, text="📌 全域設定 - 人名對照（套用到所有圖片）", font=('Arial', 10, 'bold'))
        global_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 3))

        ttk.Label(custom_frame, text="格式：原文=中文（一行一個）", foreground="gray").grid(row=1, column=0, sticky=tk.W, pady=(0, 3))

        self.global_config_text = scrolledtext.ScrolledText(custom_frame, width=75, height=3, font=('Consolas', 9))
        self.global_config_text.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))
        self.global_config_text.insert('1.0', '# 範例：サトシ=小智')

        # 全域額外指示
        global_prompt_label = ttk.Label(custom_frame, text="📌 全域額外指示（套用到所有圖片）", font=('Arial', 10, 'bold'))
        global_prompt_label.grid(row=3, column=0, sticky=tk.W, pady=(0, 3))

        ttk.Label(custom_frame, text="給 AI 的額外翻譯要求（一行一個）", foreground="gray").grid(row=4, column=0, sticky=tk.W, pady=(0, 3))

        self.global_prompt_text = scrolledtext.ScrolledText(custom_frame, width=75, height=2, font=('Consolas', 9))
        self.global_prompt_text.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))
        self.global_prompt_text.insert('1.0', '# 範例：使用輕鬆幽默語氣')

        # 特定圖片設定（針對個別圖片）
        specific_label = ttk.Label(custom_frame, text="🎯 特定圖片設定（針對個別圖片）", font=('Arial', 10, 'bold'))
        specific_label.grid(row=6, column=0, sticky=tk.W, pady=(0, 3))

        ttk.Label(custom_frame, text="格式：檔名=額外要求（一行一個）", foreground="gray").grid(row=7, column=0, sticky=tk.W, pady=(0, 3))

        self.specific_config_text = scrolledtext.ScrolledText(custom_frame, width=75, height=3, font=('Consolas', 9))
        self.specific_config_text.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 3))
        self.specific_config_text.insert('1.0', '# 範例：page001.jpg=保留日文擬聲詞')

        # 控制按鈕區域
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, columnspan=3, pady=(0, 8))

        self.start_btn = ttk.Button(control_frame, text="🚀 開始翻譯", command=self.start_translation, style='Accent.TButton')
        self.start_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="⏸ 停止", command=self.stop_translation, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=5)

        ttk.Button(control_frame, text="📁 開啟輸出資料夾", command=self.open_output_folder).grid(row=0, column=2, padx=5)

        # 進度區域
        progress_frame = ttk.LabelFrame(main_frame, text="處理進度", padding="3")
        progress_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))

        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, length=600)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        self.status_label = ttk.Label(progress_frame, text="等待開始...", foreground="gray")
        self.status_label.grid(row=1, column=0, sticky=tk.W)

        # 日誌區域
        log_frame = ttk.LabelFrame(main_frame, text="處理日誌", padding="3")
        log_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E))

        self.log_text = scrolledtext.ScrolledText(log_frame, width=75, height=6, state=tk.DISABLED, font=('Consolas', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        # 設定 logging handler
        self.text_handler = TextHandler(self.log_text)
        logging.getLogger().addHandler(self.text_handler)
        logging.getLogger().setLevel(logging.INFO)

        # 版權資訊
        copyright_label = ttk.Label(main_frame, text="© 2025 Mandy | v0.1-beta",
                                   font=('Arial', 8), foreground="gray", anchor='center')
        copyright_label.grid(row=7, column=0, columnspan=3, pady=(10, 0))

    def show_api_help(self):
        """顯示 API Key 說明"""
        help_text = """如何取得 Gemini API Key：

1. 前往 Google AI Studio
   https://makersuite.google.com/app/apikey

2. 使用 Google 帳號登入

3. 點擊「Create API Key」建立 API Key

4. 複製 API Key 並貼到上方欄位

注意：API Key 是私密資訊，請勿分享給他人！"""

        messagebox.showinfo("取得 API Key", help_text)

    def browse_input_dir(self):
        """選擇輸入資料夾"""
        directory = filedialog.askdirectory(title="選擇輸入資料夾（放置日文漫畫圖片）")
        if directory:
            self.input_dir_var.set(directory)
            self.save_config()

    def browse_output_dir(self):
        """選擇輸出資料夾"""
        directory = filedialog.askdirectory(title="選擇輸出資料夾（儲存翻譯結果）")
        if directory:
            self.output_dir_var.set(directory)
            self.save_config()

    def open_output_folder(self):
        """開啟輸出資料夾"""
        output_dir = self.output_dir_var.get()
        if output_dir and os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            messagebox.showwarning("警告", "輸出資料夾不存在！")

    def load_translation_config(self):
        """載入翻譯配置到 GUI"""
        config_file = Path("translation_config.txt")
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                    # 分割三個區塊
                    global_section = ""
                    global_prompt_section = ""
                    specific_section = ""

                    if "[全域設定]" in content:
                        parts = content.split("[全域 Prompt]")
                        global_section = parts[0].replace("[全域設定]", "").strip()

                        if len(parts) > 1:
                            remaining = parts[1]
                            if "[特定圖片]" in remaining:
                                prompt_parts = remaining.split("[特定圖片]")
                                global_prompt_section = prompt_parts[0].strip()
                                specific_section = prompt_parts[1].strip() if len(prompt_parts) > 1 else ""
                            else:
                                global_prompt_section = remaining.strip()
                        elif "[特定圖片]" in parts[0]:
                            temp_parts = parts[0].split("[特定圖片]")
                            global_section = temp_parts[0].replace("[全域設定]", "").strip()
                            specific_section = temp_parts[1].strip() if len(temp_parts) > 1 else ""

                    # 載入到 GUI
                    if global_section:
                        self.global_config_text.delete('1.0', tk.END)
                        self.global_config_text.insert('1.0', global_section)

                    if global_prompt_section:
                        self.global_prompt_text.delete('1.0', tk.END)
                        self.global_prompt_text.insert('1.0', global_prompt_section)

                    if specific_section:
                        self.specific_config_text.delete('1.0', tk.END)
                        self.specific_config_text.insert('1.0', specific_section)

            except Exception as e:
                logging.warning(f"無法載入 translation_config.txt: {e}")

    def save_translation_config(self):
        """儲存翻譯配置到檔案"""
        try:
            global_content = self.global_config_text.get('1.0', tk.END).strip()
            global_prompt_content = self.global_prompt_text.get('1.0', tk.END).strip()
            specific_content = self.specific_config_text.get('1.0', tk.END).strip()

            with open("translation_config.txt", 'w', encoding='utf-8') as f:
                f.write("[全域設定]\n")
                f.write("# 說明：這裡的人名對照會套用到「所有圖片」\n")
                f.write("# 格式：原文=中文（一行一個）\n")
                if global_content:
                    f.write(global_content)
                f.write("\n\n[全域 Prompt]\n")
                f.write("# 說明：套用到「所有圖片」的額外翻譯指示\n")
                if global_prompt_content:
                    f.write(global_prompt_content)
                f.write("\n\n[特定圖片]\n")
                f.write("# 說明：針對「個別圖片」設定額外的翻譯要求\n")
                f.write("# 格式：檔名=額外要求（一行一個）\n")
                if specific_content:
                    f.write(specific_content)
                f.write("\n")

            logging.info("已儲存翻譯配置")

        except Exception as e:
            logging.error(f"無法儲存 translation_config.txt: {e}")

    def get_extra_prompt(self):
        """取得額外提示詞（已移除此功能）"""
        return ""

    def validate_inputs(self):
        """驗證輸入"""
        if not self.api_key_var.get():
            messagebox.showerror("錯誤", "請輸入 Gemini API Key！")
            return False

        if not self.input_dir_var.get():
            messagebox.showerror("錯誤", "請選擇輸入資料夾！")
            return False

        if not os.path.exists(self.input_dir_var.get()):
            messagebox.showerror("錯誤", "輸入資料夾不存在！")
            return False

        if not self.output_dir_var.get():
            messagebox.showerror("錯誤", "請選擇輸出資料夾！")
            return False

        return True

    def start_translation(self):
        """開始翻譯"""
        if not self.validate_inputs():
            return

        # 建立輸出資料夾
        os.makedirs(self.output_dir_var.get(), exist_ok=True)

        # 更新按鈕狀態
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.is_processing = True

        # 清空日誌
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)

        # 在新執行緒中執行翻譯
        thread = threading.Thread(target=self.run_translation, daemon=True)
        thread.start()

    def stop_translation(self):
        """停止翻譯"""
        self.is_processing = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="已停止", foreground="orange")

    def run_translation(self):
        """執行翻譯（在背景執行緒中）"""
        try:
            # 設定環境變數
            os.environ["GEMINI_API_KEY"] = self.api_key_var.get()

            # 儲存翻譯配置到檔案
            self.save_translation_config()

            # 初始化 AI 引擎（會自動讀取 translation_config.txt）
            logging.info("正在初始化 AI 引擎...")
            ai_engine = AIEngine()

            # 取得圖片列表
            input_dir = self.input_dir_var.get()
            output_dir = self.output_dir_var.get()

            image_files = [f for f in os.listdir(input_dir)
                          if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]

            if not image_files:
                logging.warning(f"在 {input_dir} 找不到圖片檔案。")
                messagebox.showwarning("警告", "找不到圖片檔案！")
                self.stop_translation()
                return

            total = len(image_files)
            logging.info(f"找到 {total} 張圖片待處理。")

            # 處理每張圖片
            for i, filename in enumerate(image_files):
                if not self.is_processing:
                    logging.info("使用者中止處理。")
                    break

                input_path = os.path.join(input_dir, filename)
                output_filename = os.path.splitext(filename)[0] + ".jpg"
                output_path = os.path.join(output_dir, output_filename)

                # 檢查是否已存在
                if os.path.exists(output_path):
                    logging.info(f"[{i+1}/{total}] 檔案已存在，跳過: {output_path}")
                    self.progress_var.set(int((i + 1) / total * 100))
                    continue

                # 更新狀態
                self.status_label.config(text=f"正在處理: {filename} ({i+1}/{total})", foreground="blue")
                logging.info(f"[{i+1}/{total}] 正在處理: {input_path}")

                try:
                    # 處理圖片（name_mapping 和 extra_prompt 都從配置檔讀取，不需要參數）
                    success = ai_engine.process_image(
                        input_path,
                        output_path
                    )

                    if success:
                        logging.info(f"✓ 成功！已儲存至: {output_path}")
                    else:
                        logging.error(f"✗ 處理失敗: {filename}")

                except Exception as e:
                    logging.error(f"✗ 發生錯誤: {e}")

                # 更新進度條
                self.progress_var.set(int((i + 1) / total * 100))

            # 完成
            if self.is_processing:
                logging.info("=" * 50)
                logging.info("所有任務已完成！")
                self.status_label.config(text=f"完成！共處理 {total} 張圖片", foreground="green")
                messagebox.showinfo("完成", f"翻譯完成！\n共處理 {total} 張圖片")

        except Exception as e:
            logging.error(f"發生錯誤: {e}")
            messagebox.showerror("錯誤", f"處理失敗：{str(e)}")

        finally:
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.is_processing = False


class TextHandler(logging.Handler):
    """自訂 logging handler，將日誌輸出到 Text widget"""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.config(state=tk.NORMAL)
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.see(tk.END)
            self.text_widget.config(state=tk.DISABLED)
        self.text_widget.after(0, append)


if __name__ == "__main__":
    root = tk.Tk()
    app = ComicTranslatorGUI(root)
    root.mainloop()
