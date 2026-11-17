"""下载并安装 argostranslate 的 en→zh 离线语言包（约 70MB，一次性操作）。"""

from __future__ import annotations

import sys
import tempfile
import urllib.request
from pathlib import Path

MODEL_URL = "https://argos-net.com/v1/translate-en_zh-1_9.argosmodel"
MODEL_NAME = "translate-en_zh-1_9.argosmodel"


def _has_en_zh() -> bool:
    from argostranslate import translate

    languages = {lang.code: lang for lang in translate.get_installed_languages()}
    source, target = languages.get("en"), languages.get("zh")
    return bool(source and target and source.get_translation(target))


def _download(url: str, dest: Path) -> None:
    print(f"下载 {url}")
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (outlook-digest)"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with dest.open("wb") as fh:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r  {done / 1048576:6.1f} / {total / 1048576:.1f} MB ({pct}%)", end="")
                else:
                    print(f"\r  {done / 1048576:6.1f} MB", end="")
    print()


def main() -> int:
    try:
        from argostranslate import package
    except ImportError:
        print("未安装 argostranslate，请先运行：")
        print(r"  .venv\Scripts\python.exe -m pip install argostranslate -i https://pypi.tuna.tsinghua.edu.cn/simple")
        return 1

    if _has_en_zh():
        print("en→zh 离线语言包已安装，无需重复操作。")
        return 0

    dest = Path(tempfile.gettempdir()) / MODEL_NAME
    if not dest.exists() or dest.stat().st_size < 60 * 1024 * 1024:
        _download(MODEL_URL, dest)
    print(f"安装 {dest} …")
    package.install_from_path(dest)

    if not _has_en_zh():
        print("安装后仍检测不到 en→zh 语言包，请检查 argostranslate 版本。")
        return 1
    print("完成：en→zh 离线语言包已就绪，无需联网即可翻译标题。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
