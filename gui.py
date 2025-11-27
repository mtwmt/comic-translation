import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import logging
from pathlib import Path
from src.ai_engine import AIEngine

# 修正 Windows 高 DPI 模糊問題（改進版，相容 Win10/Win11）
try:
    from ctypes import windll
    # 設定為 System DPI Aware (適用於 Windows 10/11)
    windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except:
    try:
        # 備用方案：舊版 Windows 或上述方法失敗時
        windll.user32.SetProcessDPIAware()
    except:
        pass

class ComicTranslatorGUI:
    # 常數定義
    MIN_WIDTH = 700
    MIN_HEIGHT = 750
    SCREEN_WIDTH_RATIO = 0.7
    SCREEN_HEIGHT_RATIO = 0.85
    MAX_WIDTH = 900
    MAX_HEIGHT = 1000

    def __init__(self, root):
        self.root = root
        self.root.title("🎨 AI 漫畫翻譯工具")

        # 初始化變數
        self.is_processing = False
        self._resize_timer = None  # 用於防抖動

        # 設定視窗尺寸和位置
        self._setup_window_geometry()

        # 設定 logging
        self.setup_logging()

        # 初始化 UI 變數
        self.api_key_var = tk.StringVar()
        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()

        # 建立介面
        self.create_widgets()

        # 載入設定（延遲載入，避免阻塞 UI）
        self.root.after(100, self.load_config)

    def _setup_window_geometry(self):
        """設定視窗尺寸和位置"""
        # 強制更新以取得正確的螢幕尺寸
        self.root.update_idletasks()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # 計算視窗尺寸
        window_width = min(self.MAX_WIDTH, int(screen_width * self.SCREEN_WIDTH_RATIO))
        window_height = min(self.MAX_HEIGHT, int(screen_height * self.SCREEN_HEIGHT_RATIO))

        # 計算置中位置
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)

        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.root.resizable(True, True)

    def setup_logging(self):
        """設定 logging"""
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    def load_config(self):
        """載入上次的設定"""
        try:
            config_file = Path("gui_config.txt")
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if len(lines) >= 2:
                        self.input_dir_var.set(lines[0].strip())
                        self.output_dir_var.set(lines[1].strip())
        except Exception as e:
            logging.warning(f"無法載入 GUI 設定: {e}")

        # 載入翻譯配置
        self.load_translation_config()

    def save_config(self):
        """儲存設定"""
        try:
            with open("gui_config.txt", 'w', encoding='utf-8') as f:
                f.write(f"{self.input_dir_var.get()}\n")
                f.write(f"{self.output_dir_var.get()}\n")
        except Exception as e:
            logging.error(f"無法儲存設定: {e}")

    def on_window_resize(self, event):
        """視窗縮放時的回應（RWD）- 使用防抖動優化"""
        # 只處理主視窗的縮放事件
        if event.widget != self.root:
            return

        # 取消之前的計時器（防抖動）
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)

        # 設定新的計時器，300ms 後才執行
        self._resize_timer = self.root.after(300, self._handle_resize)

    def _handle_resize(self):
        """實際處理視窗縮放（預留給未來擴展）"""
        # 可以在這裡根據視窗大小動態調整字體等
        pass

    def create_widgets(self):
        """建立介面元件"""
        # 設定 grid 權重，讓內容可以伸縮（RWD 關鍵）
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # 主容器 - 使用相對 padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 設定 main_frame 的欄位和列權重（RWD 核心）
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(6, weight=1)  # 讓日誌區域可以擴展

        # 標題 - 響應式字體
        self.title_label = ttk.Label(main_frame, text="🎨 AI 漫畫翻譯工具", font=('Arial', 16, 'bold'), anchor='center')
        self.title_label.grid(row=0, column=0, pady=(0, 8), sticky=(tk.W, tk.E))

        # API Key 區域
        api_frame = ttk.LabelFrame(main_frame, text="API 設定", padding="8")
        api_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        api_frame.columnconfigure(1, weight=1)  # 讓輸入框可伸縮

        ttk.Label(api_frame, text="Gemini API Key:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        api_entry = ttk.Entry(api_frame, textvariable=self.api_key_var, show="*")
        api_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 8))

        help_btn = ttk.Button(api_frame, text="❓ 如何取得", command=self.show_api_help)
        help_btn.grid(row=0, column=2)

        # 資料夾選擇區域
        folder_frame = ttk.LabelFrame(main_frame, text="資料夾設定", padding="8")
        folder_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        folder_frame.columnconfigure(1, weight=1)  # 讓輸入框可伸縮

        # 輸入資料夾
        ttk.Label(folder_frame, text="輸入資料夾:").grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        ttk.Entry(folder_frame, textvariable=self.input_dir_var).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(8, 8), pady=(0, 8))
        ttk.Button(folder_frame, text="瀏覽...", command=self.browse_input_dir).grid(row=0, column=2, pady=(0, 8))

        # 輸出資料夾
        ttk.Label(folder_frame, text="輸出資料夾:").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(folder_frame, textvariable=self.output_dir_var).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(8, 8))
        ttk.Button(folder_frame, text="瀏覽...", command=self.browse_output_dir).grid(row=1, column=2)

        # 自訂翻譯設定區域
        custom_frame = ttk.LabelFrame(main_frame, text="自訂翻譯設定 (選填)", padding="8")
        custom_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        custom_frame.columnconfigure(0, weight=1)  # 讓文字框可伸縮

        # 全域設定 - 人名對照（套用到所有圖片）
        global_label = ttk.Label(custom_frame, text="📌 全域設定 - 人名對照（套用到所有圖片）", font=('Arial', 9, 'bold'))
        global_label.grid(row=0, column=0, sticky=tk.W, pady=(0, 2))

        ttk.Label(custom_frame, text="格式：原文=中文（一行一個）", foreground="gray", font=('Arial', 8)).grid(row=1, column=0, sticky=tk.W, pady=(0, 2))

        self.global_config_text = scrolledtext.ScrolledText(custom_frame, height=3, font=('Consolas', 9), wrap=tk.WORD)
        self.global_config_text.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        self.global_config_text.insert('1.0', '# 範例：サトシ=小智')

        # 全域額外指示
        global_prompt_label = ttk.Label(custom_frame, text="📌 全域額外指示（套用到所有圖片）", font=('Arial', 9, 'bold'))
        global_prompt_label.grid(row=3, column=0, sticky=tk.W, pady=(0, 2))

        ttk.Label(custom_frame, text="給 AI 的額外翻譯要求（一行一個）", foreground="gray", font=('Arial', 8)).grid(row=4, column=0, sticky=tk.W, pady=(0, 2))

        self.global_prompt_text = scrolledtext.ScrolledText(custom_frame, height=2, font=('Consolas', 9), wrap=tk.WORD)
        self.global_prompt_text.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        self.global_prompt_text.insert('1.0', '# 範例：使用輕鬆幽默語氣')

        # 特定圖片設定（針對個別圖片）
        specific_label = ttk.Label(custom_frame, text="🎯 特定圖片設定（針對個別圖片）", font=('Arial', 9, 'bold'))
        specific_label.grid(row=6, column=0, sticky=tk.W, pady=(0, 2))

        ttk.Label(custom_frame, text="格式：檔名=額外要求（一行一個）", foreground="gray", font=('Arial', 8)).grid(row=7, column=0, sticky=tk.W, pady=(0, 2))

        self.specific_config_text = scrolledtext.ScrolledText(custom_frame, height=3, font=('Consolas', 9), wrap=tk.WORD)
        self.specific_config_text.grid(row=8, column=0, sticky=(tk.W, tk.E), pady=(0, 2))
        self.specific_config_text.insert('1.0', '# 範例：page001.jpg=保留日文擬聲詞')

        # 控制按鈕區域
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, pady=(0, 6))

        self.start_btn = ttk.Button(control_frame, text="🚀 開始翻譯", command=self.start_translation, style='Accent.TButton')
        self.start_btn.grid(row=0, column=0, padx=4)

        self.stop_btn = ttk.Button(control_frame, text="⏸ 停止", command=self.stop_translation, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=1, padx=4)

        ttk.Button(control_frame, text="📁 開啟輸出資料夾", command=self.open_output_folder).grid(row=0, column=2, padx=4)

        # 進度區域
        progress_frame = ttk.LabelFrame(main_frame, text="處理進度", padding="8")
        progress_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 6))
        progress_frame.columnconfigure(0, weight=1)  # 讓進度條可伸縮

        self.progress_var = tk.IntVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 4))

        self.status_label = ttk.Label(progress_frame, text="等待開始...", foreground="gray")
        self.status_label.grid(row=1, column=0, sticky=tk.W)

        # 日誌區域（可伸縮）
        log_frame = ttk.LabelFrame(main_frame, text="處理日誌", padding="8")
        log_frame.grid(row=6, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)  # 讓日誌框可伸縮
        log_frame.rowconfigure(0, weight=1)  # 讓日誌框可垂直伸縮

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, state=tk.DISABLED, font=('Consolas', 9), wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 設定 logging handler
        self.text_handler = TextHandler(self.log_text)
        logging.getLogger().addHandler(self.text_handler)
        logging.getLogger().setLevel(logging.INFO)

        # 版權資訊
        copyright_label = ttk.Label(main_frame, text="© 2025 Mandy | v0.2-beta",
                                   font=('Arial', 8), foreground="gray", anchor='center')
        copyright_label.grid(row=7, column=0, pady=(6, 0), sticky=(tk.W, tk.E))

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
        if not config_file.exists():
            return

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 使用字典來解析配置區塊（更清晰的結構）
            sections = self._parse_config_sections(content)

            # 載入到 GUI
            self._load_section_to_widget(sections.get("全域設定", ""), self.global_config_text)
            self._load_section_to_widget(sections.get("全域 Prompt", ""), self.global_prompt_text)
            self._load_section_to_widget(sections.get("特定圖片", ""), self.specific_config_text)

        except Exception as e:
            logging.warning(f"無法載入 translation_config.txt: {e}")

    def _parse_config_sections(self, content):
        """解析配置文件區塊"""
        sections = {}
        current_section = None
        current_content = []

        for line in content.split('\n'):
            # 檢查是否為區塊標題
            if line.strip().startswith('[') and line.strip().endswith(']'):
                # 儲存前一個區塊
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                # 開始新區塊
                current_section = line.strip()[1:-1]
                current_content = []
            elif current_section:
                # 過濾掉註解說明行
                if not line.strip().startswith('# 說明：') and not line.strip().startswith('# 格式：'):
                    current_content.append(line)

        # 儲存最後一個區塊
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()

        return sections

    def _load_section_to_widget(self, content, widget):
        """載入配置內容到文字元件"""
        if content:
            widget.delete('1.0', tk.END)
            widget.insert('1.0', content)

    def save_translation_config(self):
        """儲存翻譯配置到檔案"""
        try:
            # 取得各區塊內容
            sections = {
                "全域設定": self.global_config_text.get('1.0', tk.END).strip(),
                "全域 Prompt": self.global_prompt_text.get('1.0', tk.END).strip(),
                "特定圖片": self.specific_config_text.get('1.0', tk.END).strip()
            }

            # 建立配置內容
            config_lines = []

            # 全域設定區塊
            config_lines.extend([
                "[全域設定]",
                "# 說明：這裡的人名對照會套用到「所有圖片」",
                "# 格式：原文=中文（一行一個）",
                sections["全域設定"] if sections["全域設定"] else "",
                ""
            ])

            # 全域 Prompt 區塊
            config_lines.extend([
                "[全域 Prompt]",
                "# 說明：套用到「所有圖片」的額外翻譯指示",
                sections["全域 Prompt"] if sections["全域 Prompt"] else "",
                ""
            ])

            # 特定圖片區塊
            config_lines.extend([
                "[特定圖片]",
                "# 說明：針對「個別圖片」設定額外的翻譯要求",
                "# 格式：檔名=額外要求（一行一個）",
                sections["特定圖片"] if sections["特定圖片"] else "",
                ""
            ])

            # 寫入檔案
            with open("translation_config.txt", 'w', encoding='utf-8') as f:
                f.write('\n'.join(config_lines))

            logging.info("已儲存翻譯配置")

        except Exception as e:
            logging.error(f"無法儲存 translation_config.txt: {e}")

    def validate_inputs(self):
        """驗證輸入"""
        validations = [
            (self.api_key_var.get(), "請輸入 Gemini API Key！"),
            (self.input_dir_var.get(), "請選擇輸入資料夾！"),
            (os.path.exists(self.input_dir_var.get()) if self.input_dir_var.get() else False, "輸入資料夾不存在！"),
            (self.output_dir_var.get(), "請選擇輸出資料夾！")
        ]

        for condition, error_msg in validations:
            if not condition:
                messagebox.showerror("錯誤", error_msg)
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

            # 初始化 AI 引擎
            logging.info("正在初始化 AI 引擎...")
            ai_engine = AIEngine()

            # 取得圖片列表
            input_dir = self.input_dir_var.get()
            output_dir = self.output_dir_var.get()

            image_files = self._get_image_files(input_dir)

            if not image_files:
                logging.warning(f"在 {input_dir} 找不到圖片檔案。")
                messagebox.showwarning("警告", "找不到圖片檔案！")
                self.stop_translation()
                return

            total = len(image_files)
            logging.info(f"找到 {total} 張圖片待處理。")

            # 處理每張圖片
            success_count = 0
            skip_count = 0

            for i, filename in enumerate(image_files, 1):
                if not self.is_processing:
                    logging.info("使用者中止處理。")
                    break

                result = self._process_single_image(ai_engine, input_dir, output_dir, filename, i, total)

                if result == "success":
                    success_count += 1
                elif result == "skip":
                    skip_count += 1

                # 更新進度條
                self.progress_var.set(int(i / total * 100))

            # 完成
            if self.is_processing:
                logging.info("=" * 50)
                logging.info(f"所有任務已完成！成功: {success_count}, 跳過: {skip_count}, 失敗: {total - success_count - skip_count}")
                self.status_label.config(text=f"完成！成功 {success_count} 張", foreground="green")
                messagebox.showinfo("完成", f"翻譯完成！\n成功: {success_count}\n跳過: {skip_count}\n失敗: {total - success_count - skip_count}")

        except Exception as e:
            logging.error(f"發生錯誤: {e}", exc_info=True)
            messagebox.showerror("錯誤", f"處理失敗：{str(e)}")

        finally:
            self._reset_ui_state()

    def _get_image_files(self, directory):
        """取得資料夾中的圖片檔案"""
        supported_formats = ('.png', '.jpg', '.jpeg', '.webp')
        try:
            return [f for f in os.listdir(directory) if f.lower().endswith(supported_formats)]
        except Exception as e:
            logging.error(f"無法讀取資料夾 {directory}: {e}")
            return []

    def _process_single_image(self, ai_engine, input_dir, output_dir, filename, index, total):
        """處理單張圖片"""
        input_path = os.path.join(input_dir, filename)
        output_filename = os.path.splitext(filename)[0] + ".jpg"
        output_path = os.path.join(output_dir, output_filename)

        # 檢查是否已存在
        if os.path.exists(output_path):
            logging.info(f"[{index}/{total}] 檔案已存在，跳過: {output_path}")
            return "skip"

        # 更新狀態
        self.status_label.config(text=f"正在處理: {filename} ({index}/{total})", foreground="blue")
        logging.info(f"[{index}/{total}] 正在處理: {input_path}")

        try:
            success = ai_engine.process_image(input_path, output_path)

            if success:
                logging.info(f"✓ 成功！已儲存至: {output_path}")
                return "success"
            else:
                logging.error(f"✗ 處理失敗: {filename}")
                return "failed"

        except Exception as e:
            logging.error(f"✗ 發生錯誤: {e}")
            return "failed"

    def _reset_ui_state(self):
        """重置 UI 狀態"""
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
