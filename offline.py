"""CLI for local image analysis/revision and opt-in subscription text translation."""
from pathlib import Path
import argparse


def main():
    parser = argparse.ArgumentParser(description="日文漫畫 → 繁體中文，本機圖片處理／訂閱 CLI 文字翻譯")
    parser.add_argument("--models", type=Path, default=Path(__file__).parent / "models")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prepare-models", help="下載本機文字偵測及 OCR 模型")
    sub.add_parser("prepare-restoration", help="下載並驗證漫畫遮罩與 LaMa 局部修補模型（約 300 MB）")
    analyze = sub.add_parser("analyze", help="只在本機辨識與建立可編輯遮罩，不呼叫雲端翻譯")
    analyze.add_argument("input", type=Path)
    analyze.add_argument("--report", type=Path, required=True)
    review = sub.add_parser("review", help="開啟本機修訂器；按「翻譯此區」才呼叫所選翻譯引擎")
    review.add_argument("report", type=Path)
    translate = sub.add_parser("translate")
    translate.add_argument("inputs", type=Path, nargs="+")
    translate.add_argument("--output", type=Path)
    translate.add_argument("--glossary", type=Path)
    resume = sub.add_parser("resume")
    resume.add_argument("journal", type=Path)
    resume.add_argument("--retry-failed", action="store_true")
    resume.add_argument("--retry-partial", action="store_true")
    for command in (translate, resume):
        command.add_argument("--allow-cloud-text", action="store_true", help="同意將辨識日文及名稱表送至所選翻譯引擎；圖片留本機")
        command.add_argument("--provider", choices=["agy", "claude", "codex"],
                             help="翻譯引擎（預設用 GUI 儲存的設定，沒有則 agy）")
        command.add_argument("--model", help="模型名稱（預設用 GUI 儲存的設定）")
        command.add_argument("--restoration", choices=["auto", "legacy", "enhanced"], default="auto")
    args = parser.parse_args()
    if args.command == "prepare-models":
        from src.offline.models import prepare_models
        prepare_models(args.models)
        return
    if args.command == "prepare-restoration":
        from src.offline.restoration import prepare_restoration_models
        prepare_restoration_models(args.models)
        return
    if args.command == "review":
        from src.offline.review_gui import open_review
        open_review(args.report, args.models)
        return
    if args.command == "analyze":
        if args.report.exists():
            parser.error("報告已存在，請使用新的檔名")
        from src.offline.pipeline import TranslationPipeline
        from src.offline.storage import atomic_json
        pipeline = TranslationPipeline(args.models, restoration="enhanced")
        _, report, _ = pipeline.process(args.input, {}, print, analyze_only=True)
        atomic_json(args.report, report)
        print(f"本機辨識報告：{args.report}")
        return
    if not args.allow_cloud_text:
        parser.error("雲端文字翻譯需要 --allow-cloud-text 同意傳送日文與固定名稱；圖片不傳送。")
    from src.offline.pipeline import TranslationPipeline
    from src.offline.batch import BatchRunner, create_batch, parse_glossary
    from src.offline.translators import DEFAULT_PROVIDER, create_translator
    from src.offline.translators import translator_from_settings
    translator = (create_translator(args.provider, args.model) if args.provider
                  else translator_from_settings() if not args.model else create_translator(DEFAULT_PROVIDER, args.model))
    options = {} if args.restoration == "auto" else {"restoration": args.restoration}
    pipeline = TranslationPipeline(args.models, translator=translator, **options)
    if args.command == "translate":
        glossary = parse_glossary(args.glossary.read_text(encoding="utf-8") if args.glossary else "")
        journal = create_batch(args.inputs, pipeline.fingerprint, glossary, args.output)
    else:
        journal = args.journal
    print(f"工作紀錄：{journal}", flush=True)
    runner = BatchRunner(pipeline, lambda event: print(event, flush=True))
    try:
        result = runner.run(journal, retry_failed=getattr(args, "retry_failed", False),
                            retry_partial=getattr(args, "retry_partial", False))
    except KeyboardInterrupt:
        print("已中斷；可用 resume 恢復。")
        return
    print(result, flush=True)


if __name__ == "__main__":
    main()
