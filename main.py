# main.py
import os
import cv2
from Shamir_share.test_Shamir import test_shamir
from CRT_share.test_CRT       import test_crt
from performance              import performance, _fmt_bytes
from report                   import Reporter
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- 默认参数 ----
ADDR   = './perf_out/'
REPEAT = 10


def _results_to_table(results):
    headers = ["算法", "n", "k", "chunk",
               "分片 avg (ms)", "恢复 avg (ms)",
               "单 share", "总 share", "max_err", "完全恢复"]
    rows = []
    for r in results:
        chunk = f"{r['chunk_bytes']}B" if r['chunk_bytes'] else "-"
        rows.append([
            r['algorithm'], r['n'], r['k'], chunk,
            f"{r['t_gen_avg']*1000:.2f}",
            f"{r['t_rec_avg']*1000:.2f}",
            _fmt_bytes(r['single_size']),
            _fmt_bytes(r['total_size']),
            r['max_err'],
            '✅' if r['exact'] else '❌',
        ])
    return headers, rows


def _results_to_table_min(results):
    headers = ["算法", "n", "k", "chunk",
               "分片 min (ms)", "恢复 min (ms)"]
    rows = []
    for r in results:
        chunk = f"{r['chunk_bytes']}B" if r['chunk_bytes'] else "-"
        rows.append([
            r['algorithm'], r['n'], r['k'], chunk,
            f"{r['t_gen_min']*1000:.2f}",
            f"{r['t_rec_min']*1000:.2f}",
        ])
    return headers, rows

def main():
    img_path = os.path.join(HERE, 'shamir_test_rgb.png')
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(img_path)

    report_path = os.path.join(HERE, "report.md")

    with Reporter(report_path, title="CRT / Shamir 门限秘密共享测试报告") as R:

        # ---------------- 环境 ----------------
        R.h1("0. 测试环境")
        R.p(f"- 图像文件：`{img_path}`")
        R.p(f"- 尺寸：`{img.shape}`，dtype=`{img.dtype}`，像素数 `{img.size}`")
        R.p(f"- 文件字节：`{os.path.getsize(img_path)}` 字节")
        R.p(f"- Python 文件根目录：`{HERE}`")

        # ---------------- 基础参数 ----------------
        p, n, k = 257, 5, 3
        test = [[1, 2, 3], [1, 4, 5]]

        R.h1("1. 基础参数测试")
        R.p(f"- 参数：`k={k}, p={p}, n={n}`")
        R.p(f"- 测试份额组合：`{test}`")

        R.h2("1.1 Shamir")
        with R.capture():
            test_shamir(p, n, k, test, './given_test/')

        R.h2("1.2 CRT")
        with R.capture():
            test_crt(n, k, test, './given_test/')

        # ---------------- 自拟参数 ----------------
        k, p, n = 5, 257, 10
        test = [[1, 3, 5, 7, 9], [2, 4, 6, 8, 10], [1, 2, 4, 5, 8]]

        R.h1("2. 自拟参数测试")
        R.p(f"- 参数：`k={k}, p={p}, n={n}`")
        R.code(f"test = {test}", lang="python")

        R.h2("2.1 Shamir")
        with R.capture():
            test_shamir(p, n, k, test, './my_test/')

        R.h2("2.2 CRT")
        with R.capture():
            test_crt(n, k, test, './my_test/')

        # ---------------- 性能测试 ----------------
        SHAMIR_CASES = [(257,  5, 3), (257, 10, 5)]
        CRT_CASES    = [(5, 3), (10, 5)]

        R.h1("3. 性能测试")
        R.p(f"- 重复次数 `REPEAT = {REPEAT}`")
        R.p(f"- Shamir 参数：`{SHAMIR_CASES}`")
        R.p(f"- CRT 参数：`{CRT_CASES}`")

        with R.capture():
            results = performance(SHAMIR_CASES, CRT_CASES, ADDR, REPEAT)

        # ---- 汇总表（md 表格） ----
        R.h2("3.1 汇总（平均值）")
        headers, rows = _results_to_table(results)
        R.table(headers, rows)

        R.h2("3.2 汇总（最小值）")
        headers2, rows2 = _results_to_table_min(results)
        R.table(headers2, rows2)

        # ---- 结论 ----
        R.h1("4. 结论")
        R.p("- Shamir：份额体积 = 原图体积，恢复结果与原始像素完全一致。")
        R.p("- CRT：按 8 字节（64 bit）分组做 Asmuth-Bloom 共享，"
            "恢复产物与原文件字节完全一致（含 SHA-256 校验）。")
        R.p("- CRT 的 `m0=65b, m_i=80b`，膨胀约 1.25×，"
            "分组粒度与安全性可通过 `chunk_bytes` 调节。")
        R.p(f"- 详细数据见 `performance_result.json`。")
if __name__ == "__main__":
    main()