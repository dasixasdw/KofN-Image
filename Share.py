# Share.py
from dataclasses import dataclass
import json
import numpy as np


# =========================================================================
# 自适应整数容器
# =========================================================================
class Values:
    """按数据范围自动选最紧凑存储的整数序列容器。

    对外提供：索引、迭代、长度、size、shape、dtype、tolist、to_array。
    对内存储策略（按优先级）：
        u8 / u16 / u32 / u64         —— 无符号整数
        i8 / i16 / i32 / i64         —— 有符号整数
        limb64xN                     —— 超出 uint64 的无符号大整数
        object                       —— 仅当输入为非整数（字符串/复数等）
    """

    _UNSIGNED = (np.uint8, np.uint16, np.uint32, np.uint64)
    _SIGNED   = (np.int8,  np.int16,  np.int32,  np.int64)

    # -------------------- 构造 --------------------
    def __init__(self, data):
        if isinstance(data, Values):
            self._tag = data._tag
            self._arr = data._arr
        else:
            self._tag, self._arr = self._pack(data)

    # -------------------- 打包 --------------------
    @classmethod
    def _pack(cls, data):
        arr = np.asarray(data)

        if arr.dtype == object:
            try:
                ints = [int(v) for v in arr.ravel()]
            except (TypeError, ValueError):
                return "object", np.array(list(arr.ravel()), dtype=object)
        elif arr.dtype.kind in "iub":
            ints = [int(v) for v in arr.ravel()]
        elif arr.dtype.kind == "f":
            if not np.all(np.equal(arr, np.floor(arr))):
                raise TypeError("浮点数组包含非整数值，无法作为整数序列")
            ints = [int(v) for v in arr.ravel()]
        else:
            return "object", np.array(list(arr.ravel()), dtype=object)

        if not ints:
            return "u8", np.zeros(0, dtype=np.uint8)

        lo, hi = min(ints), max(ints)

        # 有符号分支
        if lo < 0:
            for dt in cls._SIGNED:
                info = np.iinfo(dt)
                if info.min <= lo and hi <= info.max:
                    return cls._tag_of(dt), np.array(ints, dtype=dt)
            # 超出 int64 的有符号大整数 —— object 兜底
            return "object", np.array(ints, dtype=object)

        # 无符号分支
        for dt in cls._UNSIGNED:
            if hi <= np.iinfo(dt).max:
                return cls._tag_of(dt), np.array(ints, dtype=dt)

        # 超出 uint64 —— limb 拆分
        return cls._pack_limbs(ints)

    @staticmethod
    def _tag_of(dt):
        dt = np.dtype(dt)
        return ("u" if dt.kind == "u" else "i") + str(dt.itemsize * 8)

    @classmethod
    def _pack_limbs(cls, ints):
        max_bits = max(v.bit_length() for v in ints)
        L = max(1, (max_bits + 63) // 64)
        buf = np.zeros((len(ints), L), dtype=np.uint64)
        MASK = 0xFFFFFFFFFFFFFFFF
        for i, v in enumerate(ints):
            for k in range(L):
                buf[i, k] = (v >> (64 * k)) & MASK
        return f"limb64x{L}", buf

    # -------------------- 解包 --------------------
    @staticmethod
    def _unpack(tag, arr):
        """还原成 object ndarray（元素为 Python int）。"""
        if tag == "object":
            return arr
        if tag.startswith("limb64x"):
            L = int(tag[len("limb64x"):])
            N = arr.shape[0]
            out = np.empty(N, dtype=object)
            for i in range(N):
                v = 0
                for k in range(L):
                    v |= int(arr[i, k]) << (64 * k)
                out[i] = v
            return out
        return arr.astype(object)

    @classmethod
    def _packed(cls, tag, arr):
        """从磁盘直接构造 packed 形式（避免 load 时先解包再打包）。"""
        v = cls.__new__(cls)
        v._tag = str(tag)
        v._arr = arr
        return v

    # -------------------- 属性 --------------------
    @property
    def tag(self):
        return self._tag

    @property
    def raw(self):
        """底层存储（用于落盘）。"""
        return self._arr

    @property
    def dtype(self):
        return self._arr.dtype

    @property
    def size(self):
        if self._tag.startswith("limb"):
            return int(self._arr.shape[0])
        return int(self._arr.size)

    @property
    def shape(self):
        if self._tag.startswith("limb"):
            return (int(self._arr.shape[0]),)
        return tuple(self._arr.shape)

    # -------------------- 序列接口 --------------------
    def __len__(self):
        return self.size

    def __iter__(self):
        return iter(self.tolist())

    def __getitem__(self, idx):
        if self._tag.startswith("limb"):
            L = int(self._tag[len("limb64x"):])
            if isinstance(idx, slice):
                return [self[i] for i in range(*idx.indices(self.size))]
            row = self._arr[idx]
            return sum(int(row[k]) << (64 * k) for k in range(L))

        if self._tag == "object":
            if isinstance(idx, slice):
                return self._arr.ravel()[idx].tolist()
            return self._arr.ravel()[idx]

        flat = self._arr.ravel()
        if isinstance(idx, slice):
            return flat[idx].tolist()
        return int(flat[idx])

    def __array__(self, dtype=None, copy=None):
        """让 np.asarray(values) 得到一个 object ndarray。"""
        out = self._unpack(self._tag, self._arr)
        if dtype is not None:
            return out.astype(dtype)
        return out

    def tolist(self):
        if self._tag.startswith("limb"):
            L = int(self._tag[len("limb64x"):])
            N = self._arr.shape[0]
            return [
                sum(int(self._arr[i, k]) << (64 * k) for k in range(L))
                for i in range(N)
            ]
        return [int(v) for v in self._arr.ravel().tolist()]

    def to_array(self, dtype=object):
        """返回 ndarray。dtype=None 时返回底层原生 dtype。"""
        if dtype is None:
            return self._arr
        if self._tag == "object":
            return self._arr.astype(dtype)
        if self._tag.startswith("limb"):
            return self._unpack(self._tag, self._arr).astype(dtype)
        return np.asarray(self._arr, dtype=dtype)

    def __repr__(self):
        return (f"Values(tag={self._tag}, size={self.size}, "
                f"stored_shape={tuple(self._arr.shape)}, "
                f"stored_dtype={self._arr.dtype})")


# =========================================================================
# Share
# =========================================================================
class Share:
    @dataclass(frozen=True)
    class Meta:
        algorithm: str
        n: int
        k: int
        p: int = 0                       # 仅 Shamir
        mode: str = ''                   # 应用层标记（可选）
        shape: tuple = ()                # 仅 Shamir 需要
        moduli: tuple = ()               # 仅 CRT
        extra: tuple = ()                # 仅 CRT: (m0, orig_len, chunk_bytes, sha256_hex)

        def __post_init__(self):
            object.__setattr__(self, 'shape',  tuple(int(v) for v in self.shape))
            object.__setattr__(self, 'moduli', tuple(int(v) for v in self.moduli))
            object.__setattr__(self, 'extra',  tuple(self.extra))

            algo = self.algorithm.lower()
            if algo == "shamir":
                if self.p <= 0:
                    raise ValueError("Shamir 需要 p > 0")
                if self.moduli or self.extra:
                    raise ValueError("Shamir 不应带 moduli / extra")
            elif algo == "crt":
                if len(self.moduli) != self.n:
                    raise ValueError(
                        f"CRT: moduli 长度 {len(self.moduli)} != n {self.n}"
                    )
                if len(self.extra) != 4:
                    raise ValueError(
                        f"CRT: extra 长度 {len(self.extra)} != 4 "
                        f"(m0, orig_len, chunk_bytes, sha256)"
                    )
                if self.shape:
                    raise ValueError("CRT: shape 应留空（恢复目标为 bytes）")

        def to_dict(self):
            d = {
                "algorithm": str(self.algorithm),
                "n": int(self.n),
                "k": int(self.k),
                "mode": str(self.mode),
            }
            algo = self.algorithm.lower()
            if algo == "shamir":
                d["p"] = int(self.p)
                d["shape"] = [int(v) for v in self.shape]
            elif algo == "crt":
                d["moduli"] = [int(v) for v in self.moduli]
                d["extra"] = list(self.extra)
            return d

        @classmethod
        def from_dict(cls, d):
            algo = str(d["algorithm"]).lower()
            kwargs = dict(
                algorithm=str(d["algorithm"]),
                n=int(d["n"]),
                k=int(d["k"]),
                mode=str(d.get("mode", "")),
            )
            if algo == "shamir":
                kwargs["p"] = int(d["p"])
                kwargs["shape"] = tuple(int(v) for v in d.get("shape", ()))
            elif algo == "crt":
                kwargs["moduli"] = tuple(int(v) for v in d.get("moduli", ()))
                kwargs["extra"] = tuple(d.get("extra", ()))
            return cls(**kwargs)

    # ==================================================================
    def __init__(self, x, values, meta: "Share.Meta"):
        assert isinstance(meta, Share.Meta)
        self.x = int(x)
        self.meta = meta
        # values 可以是 list / ndarray / Values
        self.values = values if isinstance(values, Values) else Values(values)

    # ---- 序列化 ----
    def save(self, path):
        algo = self.meta.algorithm.lower()

        data = {
            "x":          np.int64(self.x),
            "values":     self.values.raw,
            "values_tag": np.array(str(self.values.tag)),
            "algorithm":  np.array(str(self.meta.algorithm)),
            "n":          np.int64(self.meta.n),
            "k":          np.int64(self.meta.k),
            "mode":       np.array(str(self.meta.mode)),
        }
        if algo == "shamir":
            data["p"]     = np.int64(self.meta.p)
            data["shape"] = np.array(self.meta.shape, dtype=np.int64)
        elif algo == "crt":
            data["moduli"] = np.array([str(m) for m in self.meta.moduli])
            data["extra"]  = np.array(json.dumps(list(self.meta.extra)))

        np.savez_compressed(path, **data)

    @classmethod
    def load(cls, path):
        # object 分支需要 pickle，其他情况统一 allow_pickle=False
        try:
            d = np.load(path, allow_pickle=False)
        except ValueError as e:
            if "pickle" in str(e).lower():
                d = np.load(path, allow_pickle=True)
            else:
                raise

        algo = str(d["algorithm"]).lower()

        kwargs = dict(
            algorithm=str(d["algorithm"]),
            n=int(d["n"]),
            k=int(d["k"]),
            mode=str(d["mode"]) if "mode" in d.files else "",
        )
        if algo == "shamir":
            kwargs["p"] = int(d["p"])
            if "shape" in d.files:
                kwargs["shape"] = tuple(int(v) for v in d["shape"])
        elif algo == "crt":
            kwargs["moduli"] = tuple(int(str(m)) for m in d["moduli"])
            kwargs["extra"]  = tuple(json.loads(str(d["extra"])))

        meta = cls.Meta(**kwargs)

        tag = str(d["values_tag"])
        values = Values._packed(tag, d["values"])

        return cls(x=int(d["x"]), values=values, meta=meta)

    def __repr__(self):
        m = self.meta
        return (f"Share(x={self.x}, N={self.values.size}, "
                f"algorithm={m.algorithm}, n={m.n}, k={m.k}, "
                f"mode={m.mode}, values={self.values.tag})")