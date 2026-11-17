from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta

from .analyze import build_analyzer
from .archive import rebuild_day_index, rebuild_month_index, write_mail
from .config import Config, load_config
from .models import Mail
from .outlook_source import OutlookSource
from .render import render_mail
from .store import Store
from .translate import GlossaryTranslator, build_translator

log = logging.getLogger("outlook_digest")


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def setup_logging(cfg: Config, verbose: bool) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.FileHandler(
            cfg.log_dir / f"run-{datetime.now():%Y%m%d}.log", encoding="utf-8"
        )
    ]
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
    for noisy in ("argostranslate", "stanza", "ctranslate2", "spacy"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _skip_reason(mail: Mail, cfg: Config) -> str | None:
    sender = (mail.sender_email or "").lower()
    for blocked in cfg.filters.skip_senders:
        if blocked and blocked in sender:
            return f"发件人命中 {blocked}"
    searchable = "\n".join(
        [
            (mail.subject or "").lower(),
            (mail.title_norm or "").lower(),
            (mail.conversation_topic or "").lower(),
        ]
    )
    for keyword in cfg.filters.skip_subject_keywords:
        if keyword and keyword in searchable:
            return f"主题命中 {keyword}"
    if cfg.filters.include_keywords:
        if not any(kw and kw in searchable for kw in cfg.filters.include_keywords):
            return "未命中包含关键词"
    folder = (mail.folder or "").lower()
    for folder_rule in cfg.folders.skip_folders:
        if folder_rule and folder_rule.lower() in folder:
            return f"文件夹命中 {folder_rule}"
    return None


def _build_translator(cfg: Config):
    try:
        return build_translator(cfg)
    except Exception as exc:
        log.warning("翻译引擎不可用，回退到术语表：%s", exc)
        return GlossaryTranslator(cfg.glossary)


def cmd_run(cfg: Config, args) -> int:
    store = Store(cfg.db_path)
    hours = args.hours or cfg.general.lookback_hours
    limit = args.limit or cfg.general.max_per_run
    since = datetime.now() - timedelta(hours=hours)
    analyzer = build_analyzer(cfg)
    translator = _build_translator(cfg)

    log.info(
        "开始运行 provider=%s translate=%s dry_run=%s since=%s limit=%d",
        cfg.ai.provider,
        translator.engine,
        args.dry_run,
        since.strftime("%Y-%m-%d %H:%M"),
        limit,
    )
    run_id = store.start_run()
    scanned = inserted = skipped = 0
    touched_days: set[str] = set()
    touched_months: set[str] = set()
    try:
        with OutlookSource(cfg.folders.include, cfg.general.max_scan) as source:
            for mail in source.iter_mails(since, limit):
                scanned += 1
                if store.has(mail.msg_key):
                    skipped += 1
                    continue
                mail.title_norm = translator.translate(
                    mail.subject or mail.conversation_topic
                )
                reason = _skip_reason(mail, cfg)
                if reason:
                    skipped += 1
                    log.debug("跳过（%s）: %s", reason, mail.subject)
                    continue

                analysis = analyzer.analyze(mail)

                if args.dry_run:
                    print("\n" + "=" * 72)
                    print(render_mail(mail, analysis)[:2000])
                    continue

                path = write_mail(cfg, mail, analysis)
                store.insert(mail, analysis, str(path))
                inserted += 1
                day = mail.received_at.strftime("%Y-%m-%d")
                touched_days.add(day)
                touched_months.add(day[:7])
                log.info(
                    "已归档 [P%d|%s|%s] %s -> %s",
                    analysis.priority,
                    analysis.category,
                    analysis.engine,
                    (mail.subject or "(无主题)")[:40],
                    path.name,
                )
            if source.body_blocked:
                log.warning("正文访问被企业策略阻断，本次为元数据归档（主题/时间/已读状态）")

        if not args.dry_run:
            for day in sorted(touched_days):
                rebuild_day_index(cfg, day, store.rows_for_day(day))
            for month in sorted(touched_months):
                rebuild_month_index(cfg, month, store.rows_for_month(month))
        store.finish_run(
            run_id,
            scanned=scanned,
            inserted=inserted,
            skipped=skipped,
            errors=0,
            note="dry-run" if args.dry_run else "",
        )
        log.info("完成：扫描 %d，跳过 %d，归档 %d", scanned, skipped, inserted)
        return 0
    except Exception:
        store.finish_run(
            run_id, scanned=scanned, inserted=inserted, skipped=skipped, errors=1, note="exception"
        )
        raise
    finally:
        store.close()


def cmd_status(cfg: Config) -> int:
    store = Store(cfg.db_path)
    try:
        stats = store.stats()
    finally:
        store.close()
    print(f"数据库: {cfg.db_path}")
    print(f"已归档总数: {stats['total']}  今日: {stats['today']}")
    last = stats["last_run"]
    if last:
        print(
            "上次运行: {started_at} → {finished_at}  扫描 {scanned} / 归档 {inserted} / 跳过 {skipped} / 错误 {errors}".format(
                **last
            )
        )
    else:
        print("尚未运行过")
    print(f"归档目录: {cfg.archive_root}")
    return 0


def cmd_reindex(cfg: Config, args) -> int:
    store = Store(cfg.db_path)
    try:
        days = store.days_with_mails(args.days)
        for day in days:
            path = rebuild_day_index(cfg, day, store.rows_for_day(day))
            print(f"重建 {path}")
        for month in sorted({day[:7] for day in days}):
            path = rebuild_month_index(cfg, month, store.rows_for_month(month))
            print(f"重建 {path}")
    finally:
        store.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="outlook-digest", description="Outlook 邮件定时归档")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="读取新邮件并分析归档")
    run.add_argument("--hours", type=int, help="回看小时数（默认取配置）")
    run.add_argument("--limit", type=int, help="本次最多处理多少封（默认取配置）")
    run.add_argument("--dry-run", action="store_true", help="只打印不落库不写文件")
    run.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("status", help="查看累计统计与上次运行结果")

    reindex = sub.add_parser("reindex", help="重建每日索引")
    reindex.add_argument("--days", type=int, default=7, help="重建最近 N 天（默认 7）")
    reindex.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = build_parser().parse_args(argv)
    cfg = load_config()
    setup_logging(cfg, getattr(args, "verbose", False))
    try:
        if args.cmd == "run":
            return cmd_run(cfg, args)
        if args.cmd == "status":
            return cmd_status(cfg)
        if args.cmd == "reindex":
            return cmd_reindex(cfg, args)
    except Exception:
        log.exception("运行失败")
        return 1
    return 0
