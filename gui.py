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
        self.root.geometry("820x780")
        self.root.resizable(False, False)
        # self.root.minsize(860, 750)

        # 設定 logging
        self.setup_logging()

        # 變數
        self.api_key_var = tk.StringVar()
        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.is_processing = False

        # 載入上次的設定
        self.load_config()

        # 建立介面
        self.create_widgets()

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
        custom_frame = ttk.LabelFrame(main_frame, text="自訂翻譯設定 (選填)", padding="3")
        custom_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 8))

        # 人名對照表
        ttk.Label(custom_frame, text="人名對照表 (格式：原文=中文，一行一個)").grid(row=0, column=0, sticky=tk.W, pady=(0, 3))

        self.name_mapping_text = scrolledtext.ScrolledText(custom_frame, width=75, height=4, font=('Consolas', 9))
        self.name_mapping_text.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 3))
        self.name_mapping_text.insert('1.0', '# 範例：\n# サトシ=小智\n# ピカチュウ=皮卡丘\n# John=約翰')

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

    def parse_name_mapping(self):
        """解析人名對照表"""
        name_mapping = {}
        text = self.name_mapping_text.get('1.0', tk.END)

        for line in text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                if '=' in line:
                    try:
                        original, translation = line.split('=', 1)
                        name_mapping[original.strip()] = translation.strip()
                    except:
                        pass

        return name_mapping

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

            # 取得人名對照和額外提示
            name_mapping = self.parse_name_mapping()
            extra_prompt = self.get_extra_prompt()

            # 初始化 AI 引擎
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
                    # 處理圖片
                    success = ai_engine.process_image(
                        input_path,
                        output_path,
                        name_mapping=name_mapping,
                        extra_prompt=extra_prompt
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
