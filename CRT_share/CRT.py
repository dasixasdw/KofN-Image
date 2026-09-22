# CRT_share/CRT.py
import os
import hashlib
import secrets
import numpy as np

from Share import Share


# =====================================================================
# 常量
# =====================================================================
CHUNK_BYTES = 8          # 64 bit 分组
M0_BITS     = 65         # m0 > 2^64 - 1
MI_BITS     = 80         # m_i 满足 Asmuth-Bloom


# =====================================================================
# 素数工具
# =====================================================================
def _is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(40):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits):
    if bits < 2:
        raise ValueError(f"bits 太小: {bits}")
    while True:
        p = secrets.randbits(bits) | 1 | (1 << (bits - 1))
        if _is_prime(p):
            return p


def _gen_moduli(m0, n, k, bits=MI_BITS):
    """
    生成 n 个两两互素、递增、满足 Asmuth-Bloom 的素数模数。
    修复：不用集合推导，避免 bits 太小时死循环。
    """
    while True:
        moduli = []
        seen = set()
        while len(moduli) < n:
            p = _gen_prime(bits)
            if p in seen or p <= m0:
                continue
            seen.add(p)
            moduli.append(p)
        moduli.sort()

        lhs = 1
        for x in moduli[:k]:
            lhs *= x
        rhs = m0
        for x in moduli[n - k + 1:]:
            rhs *= x
        if lhs > rhs:
            return moduli


# =====================================================================
# 输入归一化
# =====================================================================
def _to_bytes(img):
    """
    把任意支持输入转成 (raw_bytes, shape, dtype_str)。
    - bytes / bytearray / memoryview
    - str / os.PathLike  → 读文件
    - numpy.ndarray      → .tobytes()
    """
    if isinstance(img, (bytes, bytearray, memoryview)):
        raw = bytes(img)
        return raw, (len(raw),), "|u1"
    if isinstance(img, (str, os.PathLike)):
        with open(img, 'rb') as f:
            raw = f.read()
        return raw, (len(raw),), "|u1"
    if isinstance(img, np.ndarray):
        arr = np.ascontiguousarray(img, dtype=np.uint8)
        return arr.tobytes(), tuple(int(v) for v in arr.shape), arr.dtype.str
    raise TypeError(f"不支持的 img 类型: {type(img)}")


# =====================================================================
# 生成
# =====================================================================
def GenShare(img, n, k, chunk_bytes=CHUNK_BYTES):
    """
    Asmuth-Bloom CRT 门限秘密共享（按字节流，64 bit 分组）。

    方案 A：m0 内部自动生成，不暴露给调用方，存在 meta.extra[0]。

    参数：
        img         : bytes / str / PathLike / np.ndarray
        n           : 参与者数
        k           : 门限
        chunk_bytes : 分组字节数（默认 8 = 64 bit）

    返回：
        list[Share]，长度 n，x = 1..n
        meta.extra = (m0, orig_len, chunk_bytes, sha256_hex)
    """
    # ---- 0. 参数检查 ----
    if not (1 <= k <= n):
        raise ValueError(f"必须 1 <= k <= n，当前 k={k}, n={n}")
    if chunk_bytes < 1:
        raise ValueError(f"chunk_bytes 必须 >= 1，当前 {chunk_bytes}")
    if M0_BITS <= 8 * chunk_bytes:
        raise ValueError(
            f"M0_BITS={M0_BITS} 必须 > 8*chunk_bytes={8*chunk_bytes}"
        )

    # ---- 1. 输入 → raw bytes ----
    raw, shape, dtype_str = _to_bytes(img)
    orig_len = len(raw)
    padding = (-orig_len) % chunk_bytes
    if padding:
        raw = raw + b'\x00' * padding
    N = len(raw) // chunk_bytes
    if N == 0:
        raise ValueError("输入为空，无法分片")

    # ---- 2. m0 自动生成（方案 A）----
    m0 = _gen_prime(M0_BITS)
    moduli = _gen_moduli(m0, n, k)

    M = 1
    for x in moduli[:k]:
        M *= x
    A_max = (M - m0) // m0
    if A_max < 0:
        raise ValueError("M 太小，无法满足 Asmuth-Bloom")

    # ---- 3. 逐块生成份额 ----
    shares_vals = [[] for _ in range(n)]
    for j in range(N):
        block = raw[j * chunk_bytes:(j + 1) * chunk_bytes]
        S = int.from_bytes(block, 'big')
        A = secrets.randbelow(A_max + 1)
        Y = S + A * m0
        for i in range(n):
            shares_vals[i].append(Y % moduli[i])

    # ---- 4. 原始字节的 sha256（仅对去掉 padding 的部分）----
    sha = hashlib.sha256(raw[:orig_len]).hexdigest()

    # ---- 5. Meta（CRT 不存 p / shape；extra 4 项）----
    meta = Share.Meta(
        algorithm="CRT",
        n=n, k=k,
        p=0,                                     # ✅ 不保存 p
        mode="FILE",
        shape=(),                                # ✅ CRT 不存 shape
        moduli=tuple(moduli),
        extra=(m0, orig_len, chunk_bytes, sha),  # ✅ 4 项
    )

    return [
        Share(x=i + 1,
              values=np.array(shares_vals[i], dtype=object),
              meta=meta)
        for i in range(n)
    ]


# =====================================================================
# 恢复
# =====================================================================
def Recover(shares, verify=True):
    """
    从份额恢复文件 bytes。

    参数：
        shares : list[Share]，至少 k 份
        verify : True 时用 sha256 校验恢复结果

    返回：
        bytes —— 恢复出的完整文件内容
    """
    if len(shares) == 0:
        raise ValueError("无可用Share")

    # ---- meta 一致性 ----
    metas = [s.meta for s in shares]
    if len(set(metas)) != 1:
        raise ValueError("共享数据不一致")

    meta = metas[0]
    if meta.algorithm.lower() != "crt":
        raise ValueError(f"Recover 仅支持 CRT，当前 algorithm={meta.algorithm}")

    # ---- extra 校验 ----
    if len(meta.extra) != 4:
        raise ValueError(
            f"meta.extra 长度应为 4，实际 {len(meta.extra)}；"
            f"旧格式 share 请重新生成"
        )
    m0, orig_len, chunk_bytes, sha = meta.extra

    # ---- 门限检查 ----
    k = meta.k
    if len(shares) < k:
        raise ValueError(f"Share数过少，需要至少 {k} 份，当前 {len(shares)} 份")

    used = shares[:k]

    # ---- 校验份额索引和 moduli ----
    for s in used:
        if not (1 <= s.x <= len(s.meta.moduli)):
            raise ValueError(
                f"Share.x={s.x} 超出 moduli 范围 [1, {len(s.meta.moduli)}]"
            )
    moduli = [int(s.meta.moduli[s.x - 1]) for s in used]
    if len(set(moduli)) != k:
        raise ValueError("选取的份额出现重复模数")

    # ---- CRT 系数 ----
    M = 1
    for m in moduli:
        M *= m
    coeffs = []
    for m in moduli:
        Mi = M // m
        inv = pow(Mi, -1, m)
        coeffs.append((Mi * inv) % M)

    # ---- 逐块恢复 ----
    N = used[0].values.size
    out = bytearray()
    for j in range(N):
        Y = 0
        for s, c in zip(used, coeffs):
            Y = (Y + int(s.values[j]) * c) % M
        S = Y % m0
        out.extend(S.to_bytes(chunk_bytes, 'big'))

    # ---- 去 padding（由 orig_len 计算得出）----
    padding = (-orig_len) % chunk_bytes
    if padding:
        out = out[:-padding]
    data = bytes(out)

    if len(data) != orig_len:
        raise ValueError(
            f"恢复字节数 {len(data)} != 原始字节数 {orig_len}"
        )

    # ---- sha256 校验 ----
    if verify:
        actual = hashlib.sha256(data).hexdigest()
        if actual != sha:
            raise ValueError(
                f"恢复结果校验失败\n  expected: {sha}\n  actual:   {actual}"
            )

    return data