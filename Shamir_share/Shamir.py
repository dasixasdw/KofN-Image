from Share import Share
import numpy as np


def GenShare(p, n, k, img):
    rng = np.random.default_rng()
    secret = img.reshape(-1)
    secret = np.asarray(secret, dtype=np.int64)

    meta = Share.Meta(
        algorithm='Shamir',
        n=n,
        k=k,
        p=p,
        mode='RGB',
        shape=img.shape,
    )

    N = secret.shape[0]
    coeff     = np.zeros(shape=(k, N), dtype=np.int64)
    coeff[0]  = secret
    coeff[1:] = rng.integers(0, p, size=(k-1, N), dtype=np.int64)

    shares = []
    for i in range(n):
        x = i + 1
        y = np.zeros(N, dtype=np.int64)
        power = 1
        for j in range(k):
            y = (y + coeff[j] * power) % p
            power = (power * x) % p
        shares.append(Share(x, y, meta))
    return shares


def Recover(shares):
    if len(shares) == 0:
        raise ValueError("无可用Share")
    metas = [s.meta for s in shares]
    if len(set(metas)) != 1:
        raise ValueError("共享数据不一致")

    p     = metas[0].p
    n     = metas[0].n
    k     = metas[0].k
    mode  = metas[0].mode
    shape = tuple(metas[0].shape)

    if len(shares) < k:
        raise ValueError(f"Share数过少，需要至少 {k} 份，当前 {len(shares)} 份")

    xs = np.array([shares[j].x for j in range(k)], dtype=np.int64)
    ys = np.array([shares[j].values for j in range(k)], dtype=np.int64)
    N = ys.shape[1]

    lambdas = np.zeros(k, dtype=np.int64)
    for j in range(k):
        num = 1
        den = 1
        for i in range(k):
            if i != j:
                num = (num * (0 - int(xs[i]))) % p
                den = (den * (int(xs[j]) - int(xs[i]))) % p
        lambdas[j] = (num * pow(int(den), -1, p)) % p

    secret = np.zeros(N, dtype=np.int64)
    for j in range(k):
        secret = (secret + ys[j] * lambdas[j]) % p

    secret = secret.astype(np.uint8)
    return secret.reshape(shape)