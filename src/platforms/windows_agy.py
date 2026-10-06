"""Bounded recovery for AGY's Windows configuration-only startup stalls."""
from src.offline.cli_common import CliTimeout
from src.offline.models import ModelError

# Short restarts recover a stalled initialization quickly; the last attempt
# keeps the full single-call budget so a slow but working CLI still passes.
CONFIG_TIMEOUTS = (8, 8, 45)


def query_configuration(run, arguments):
    # /config is an internal read-only command. It contains no source text.
    # A terminated initialization may be restarted; a translation must never
    # be resubmitted because the remote request may already have completed.
    if arguments[:2] != ["-p", "/config"]:
        raise ValueError("初始化重啟只適用於 AGY /config 檢查")
    for attempt, timeout in enumerate(CONFIG_TIMEOUTS, 1):
        try:
            return run(arguments, timeout)
        except CliTimeout as error:
            if attempt == len(CONFIG_TIMEOUTS):
                raise ModelError(
                    f"AGY 登入／設定檢查初始化卡住；已嘗試 {attempt} 次，"
                    "尚未送出本頁翻譯文字。批次已暫停，可稍後續跑。") from error


def call_label(arguments, timeout):
    if arguments[:2] == ["-p", "/config"]:
        return f"AGY 登入／設定檢查（{timeout} 秒）"
    if "--input-format" in arguments:
        return f"AGY 翻譯（{timeout} 秒）"
    return "AGY"
