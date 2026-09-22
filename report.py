# report.py
import os
import sys
import io
from contextlib import contextmanager
from datetime import datetime


class _MDWriter:
    """把 write 调用转给 Reporter 的 _md"""
    def __init__(self, report):
        self.report = report

    def write(self, data):
        self.report._md(data)

    def flush(self):
        pass


class _Tee:
    """把 write 分发到多个流"""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


class Reporter:
    """
    用法：
        with Reporter("report.md", title="...") as R:
            R.h1("标题")
            R.p("段落")
            with R.capture():          # print 内容作为代码块写入
                some_func()
            R.table(headers, rows)     # Markdown 表格
    """
    def __init__(self, path, title="报告"):
        self.path = path
        self.lines = []
        self._orig_stdout = sys.stdout
        self.h1(title)
        self.p(f"> 生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")

    # ---------- 写入 ----------
    def _md(self, s):
        self.lines.append(s)

    def _echo(self, s):
        self._orig_stdout.write(s)
        self._orig_stdout.flush()

    # ---------- 结构元素 ----------
    def h1(self, t):
        self._md(f"\n# {t}\n\n")
        self._echo(f"\n{'=' * 72}\n{t}\n{'=' * 72}\n")

    def h2(self, t):
        self._md(f"\n## {t}\n\n")
        self._echo(f"\n--- {t} ---\n")

    def h3(self, t):
        self._md(f"\n### {t}\n\n")
        self._echo(f"  {t}\n")

    def p(self, t):
        self._md(f"{t}\n\n")
        self._echo(f"{t}\n")

    def code(self, text, lang=""):
        self._md(f"```{lang}\n{text.rstrip()}\n```\n\n")
        self._echo(text)

    def table(self, headers, rows):
        # ---- Markdown 表格（每行必须带 \n）----
        self._md("| " + " | ".join(str(h) for h in headers) + " |\n")
        self._md("|" + "|".join(["---"] * len(headers)) + "|\n")
        for r in rows:
            self._md("| " + " | ".join(str(c) for c in r) + " |\n")
        self._md("\n")

        # ---- 终端友好显示 ----
        self._echo("\n")
        self._echo(" | ".join(str(h) for h in headers) + "\n")
        self._echo("-" * 72 + "\n")
        for r in rows:
            self._echo(" | ".join(str(c) for c in r) + "\n")
        self._echo("\n")

    # ---------- 捕获 print 到代码块 ----------
    @contextmanager
    def capture(self, lang=""):
        buf = io.StringIO()
        old = sys.stdout
        # 只 tee 到终端 + buf，不经过 MDWriter（避免重复写入 md）
        sys.stdout = _Tee(self._orig_stdout, buf)
        try:
            yield
        finally:
            sys.stdout = old
            # 只写 md 一次，不重复 echo
            self._md(f"```{lang}\n{buf.getvalue().rstrip()}\n```\n\n")

    # ---------- 上下文管理 ----------
    def __enter__(self):
        self._orig_stdout = sys.stdout
        sys.stdout = _Tee(self._orig_stdout, _MDWriter(self))
        return self

    def __exit__(self, *args):
        sys.stdout = self._orig_stdout
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("".join(self.lines))
        self._echo(f"\n报告已保存：{self.path}\n")