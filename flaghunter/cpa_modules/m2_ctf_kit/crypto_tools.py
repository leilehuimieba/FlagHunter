"""crypto_tools.py - PentestAgent M2 CTF Kit 密码学工具集
覆盖CTF中古典密码/编码转换/现代密码/密码分析辅助/自动解题5大类。
约束: Python 3.10+, 标准库为主, 延迟加载pycryptodome, async异步,
      每个函数返回CryptoResult(不抛异常), 中文docstring."""
from __future__ import annotations
import asyncio, base64, binascii, hashlib, itertools, math, re, string, urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
@dataclass
class CryptoResult:
    """统一密码学操作结果对象。所有crypto_*函数均返回此对象，不抛异常。"""
    success: bool; output: str = ""; plaintext: str = ""; key: str = ""
    algorithm: str = ""; confidence: float = 0.0; error: str = ""
    steps: List[str] = field(default_factory=list)
    def dict(self) -> Dict[str, Any]:
        return {"success": self.success, "output": self.output, "plaintext": self.plaintext,
                "key": self.key, "algorithm": self.algorithm, "confidence": self.confidence,
                "error": self.error, "steps": self.steps}
# 英文字母频率表(ETAOIN...)
_EN_FREQ: Dict[str, float] = {
    "e": 0.127, "t": 0.091, "a": 0.082, "o": 0.075, "i": 0.070, "n": 0.067,
    "s": 0.063, "h": 0.061, "r": 0.060, "d": 0.043, "l": 0.040, "c": 0.028,
    "u": 0.028, "m": 0.024, "w": 0.024, "f": 0.022, "g": 0.020, "y": 0.020,
    "p": 0.019, "b": 0.015, "v": 0.010, "k": 0.008, "j": 0.002, "x": 0.002,
    "q": 0.001, "z": 0.001,
}
# 摩斯电码表
_MORSE: Dict[str, str] = {".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E", "..-.": "F", "--.": "G",
    "....": "H", "..": "I", ".---": "J", "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T", "..-": "U", "...-": "V", ".--": "W",
    "-..-": "X", "-.--": "Y", "--..": "Z", "----": "0", ".----": "1", "..---": "2", "...--": "3",
    "....-": "4", ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9"}
# CTF常见密码字典(Top50)
_TOP50: List[str] = ["flag", "ctf", "admin", "password", "123456", "qwerty", "password123",
    "12345678", "abc123", "iloveyou", "welcome", "princess", "dragon", "monkey", "shadow",
    "sunshine", "master", "football", "starwars", "trustno1", "harley", "batman", "hacker",
    "security", "p@ssw0rd", "P@ssw0rd", "password1", "qwertyuiop", "qazwsx", "1q2w3e4r",
    "letmein", "charlie", "michael", "mustang", "access", "love", "superman", "hello",
    "freedom", "matrix", "secret", "summer", "cheese", "killer", "george", "cookie",
    "coffee", "yellow", "brandon", "admin123"]
def _ic(text: str) -> float:
    """计算重合指数(Index of Coincidence)。英语约0.065, 随机约0.038。"""
    letters = [c.lower() for c in text if c.isalpha()]
    n = len(letters)
    if n < 2: return 0.0
    cnt = Counter(letters)
    return sum(c * (c - 1) for c in cnt.values()) / (n * (n - 1))
def _score_en(text: str) -> float:
    """基于字母频率对文本进行英文评分(卡方风格)，越高越像英语。惩罚过度集中的字母。"""
    score = sum(_EN_FREQ.get(ch, 0.005 if ch in " \n\t.,;:!?'\"()-" else -0.05) for ch in text.lower())
    # 空格奖励
    if text and len(text) > 4:
        sr = text.count(" ") / len(text)
        if 0.05 <= sr <= 0.25: score += 0.3
    # 惩罚字母过度集中(>50%是前4高频字母etao)
    letters = [c for c in text.lower() if c.isalpha()]
    if letters:
        top4 = sum(1 for c in letters if c in "etao")
        if top4 / len(letters) > 0.55: score -= 0.4
    return score
def crypto_shift(ciphertext: str, shift: int) -> str:
    """通用移位函数(用于凯撒等)。只处理字母。"""
    res = []
    for ch in ciphertext:
        if ch.isupper(): res.append(chr((ord(ch) - 65 + shift) % 26 + 65))
        elif ch.islower(): res.append(chr((ord(ch) - 97 + shift) % 26 + 97))
        else: res.append(ch)
    return "".join(res)
def _xor(data: bytes, key: bytes) -> bytes:
    """字节流重复密钥异或。"""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
def _ok(pt: str, algo: str, conf: float = 1.0, key: str = "", steps: List[str] = None, plaintext: str = None) -> CryptoResult:
    return CryptoResult(True, output=pt, plaintext=plaintext if plaintext is not None else pt, key=key, algorithm=algo, confidence=conf, steps=steps or [])
def _err(exc: Exception, steps: List[str] = None) -> CryptoResult:
    return CryptoResult(False, error=str(exc), steps=steps or [])
def _rsa_fmt(m: int, steps: List[str], key: str, algo: str = "rsa") -> CryptoResult:
    try:
        bl = (m.bit_length() + 7) // 8
        out = m.to_bytes(bl, "big").decode("utf-8")
    except Exception: out = str(m)
    return _ok(out, algo, 1.0, key, steps)
# ─── 古典密码 ───
async def crypto_caesar(ciphertext: str, brute_force: bool = True, shift: int = None) -> CryptoResult:
    """凯撒密码。brute_force=True时尝试25种移位频率分析找最可能; 指定shift时直接解密。"""
    steps: List[str] = []
    try:
        if not brute_force and shift is None: return _err(ValueError("brute_force=False但未提供shift"), steps)
        if shift is not None: return _ok(crypto_shift(ciphertext, -shift), "caesar", 1.0, str(shift), [f"移位-{shift}解密"])
        bs, bsh, bp = -1e9, 0, ""
        for s in range(1, 26):
            pt = crypto_shift(ciphertext, -s); sc = _score_en(pt); steps.append(f"-{s}:{sc:.3f}")
            if sc > bs: bs, bsh, bp = sc, s, pt
        return _ok(bp, "caesar", min(abs(bs) / max(len(ciphertext) * 0.03, 1), 1.0), str(bsh), steps + [f"最可能移位={bsh}"])
    except Exception as exc: return _err(exc, steps)
async def crypto_vigenere(ciphertext: str, key: str = None, key_length: int = None) -> CryptoResult:
    """维吉尼亚密码。有key直接解密; 无key时通过IC推测密钥长度(2-12)再频率分析破解。"""
    steps: List[str] = []
    try:
        letters = "".join(c for c in ciphertext if c.isalpha())
        if not letters: return _err(ValueError("输入不含字母"), steps)
        if key:
            ku, res, ki = key.upper(), [], 0
            for ch in ciphertext:
                if ch.isalpha():
                    b = 65 if ch.isupper() else 97
                    res.append(chr((ord(ch) - b - (ord(ku[ki % len(ku)]) - 65)) % 26 + b)); ki += 1
                else: res.append(ch)
            return _ok("".join(res), "vigenere", 1.0, ku, [f"已知密钥'{ku}'解密"])
        best_len = key_length
        if best_len is None:
            bic, best_len = 0.0, 2
            for kl in range(2, 13):
                groups = ["".join(letters[i] for i in range(g, len(letters), kl)) for g in range(kl)]
                aic = sum(_ic(g) for g in groups) / kl; steps.append(f"kl={kl},IC={aic:.4f}")
                if aic > bic: bic, best_len = aic, kl
        kchars = []
        for gi in range(best_len):
            grp = "".join(letters[i] for i in range(gi, len(letters), best_len))
            bs_, bsh = -1e9, 0
            for s in range(26):
                sc = _score_en(crypto_shift(grp, -s))
                if sc > bs_: bs_, bsh = sc, s
            kchars.append(chr(bsh + 65))
        fkey = "".join(kchars)
        res, ki = [], 0
        for ch in ciphertext:
            if ch.isalpha():
                b = 65 if ch.isupper() else 97
                res.append(chr((ord(ch) - b - (ord(fkey[ki % len(fkey)]) - 65)) % 26 + b)); ki += 1
            else: res.append(ch)
        pt = "".join(res)
        return _ok(pt, "vigenere", min(abs(_score_en(pt)) / max(len(pt) * 0.03, 1), 1.0), fkey, steps + [f"密钥='{fkey}'"])
    except Exception as exc: return _err(exc, steps)
async def crypto_railfence(ciphertext: str, brute_force: bool = True, rails: int = None) -> CryptoResult:
    """栅栏密码。brute_force=True时尝试2-10栏。"""
    steps: List[str] = []
    def _dec(s: str, r: int) -> str:
        n, cyc = len(s), 2 * r - 2
        if cyc == 0: return s
        cnts = [0] * r
        for i in range(n):
            p = i % cyc; row = p if p < r else cyc - p; cnts[row] += 1
        cols, idx = [], 0
        for c in cnts: cols.append(s[idx:idx + c]); idx += c
        ci, row, d = [0] * r, 0, -1; out = []
        for _ in range(n):
            out.append(cols[row][ci[row]]); ci[row] += 1
            if row in (0, r - 1): d *= -1; row += d
            else: row += d
        return "".join(out)
    try:
        text = ciphertext.replace(" ", "")
        if not text: return _err(ValueError("输入为空"), steps)
        if rails is not None: return _ok(_dec(text, rails), "railfence", 1.0, str(rails), [f"指定栏数={rails}"])
        if not brute_force: return _err(ValueError("brute_force=False但未提供rails"), steps)
        bs, br, bp = -1e9, 2, ""
        for r in range(2, 11):
            pt = _dec(text, r); sc = _score_en(pt); steps.append(f"r={r}:{sc:.3f}")
            if sc > bs: bs, br, bp = sc, r, pt
        return _ok(bp, "railfence", min(abs(bs) / max(len(bp) * 0.03, 1), 1.0), str(br), steps + [f"最可能栏数={br}"])
    except Exception as exc: return _err(exc, steps)
async def crypto_atbash(ciphertext: str) -> CryptoResult:
    """Atbash密码(A<->Z, B<->Y)。直接转换。"""
    try:
        res = []
        for ch in ciphertext:
            if ch.isupper(): res.append(chr(90 - (ord(ch) - 65)))
            elif ch.islower(): res.append(chr(122 - (ord(ch) - 97)))
            else: res.append(ch)
        return _ok("".join(res), "atbash", 0.8, steps=["Atbash直接转换"])
    except Exception as exc: return _err(exc)
async def crypto_rot13(ciphertext: str) -> CryptoResult:
    """ROT13。"""
    try: return _ok(crypto_shift(ciphertext, 13), "rot13", 0.8, "13", ["ROT13解密"])
    except Exception as exc: return _err(exc)
# ─── 编码转换 ───
async def crypto_base_decode(ciphertext: str, base_type: str = "auto") -> CryptoResult:
    """Base解码。auto时自动检测Base64/32/16/85/58, 支持多层嵌套解码。"""
    steps: List[str] = []
    def _b64(s):
        try: return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4), validate=True)
        except Exception: return None
    def _b32(s):
        try: return base64.b32decode(s.upper() + "=" * ((8 - len(s) % 8) % 8), casefold=True)
        except Exception: return None
    def _b16(s):
        try: return base64.b16decode(s, casefold=True)
        except Exception: return None
    def _b85(s):
        try: return base64.b85decode(s)
        except Exception: return None
    def _b58(s):
        abc = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        num, pad = 0, len(s) - len(s.lstrip("1"))
        for ch in s:
            if ch not in abc: return None
            num = num * 58 + abc.index(ch)
        return b"\x00" * pad + num.to_bytes((num.bit_length() + 7) // 8, "big")
    decs = {"base64": _b64, "base32": _b32, "base16": _b16, "base85": _b85, "base58": _b58}
    try:
        cur = ciphertext.strip(); dec_b, used = None, ""
        if base_type == "auto":
            c = cur.replace("=", "").replace(" ", "").replace("\n", "")
            cands = []
            if re.fullmatch(r"[0-9a-fA-F]+", c) and len(c) % 2 == 0: cands.append("base16")
            if re.fullmatch(r"[A-Z2-7=]+", c.upper()): cands.append("base32")
            if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", c): cands.append("base58")
            if re.fullmatch(r"[A-Za-z0-9+/=]+", c) and len(c) % 4 in (0, 2, 3): cands.append("base64")
            if re.fullmatch(r"[A-Za-z0-9!#$%&()*+-;<=>?@^_`{|}~]+", c): cands.append("base85")
            for cand in cands:
                r = decs[cand](cur)
                if r is not None: dec_b, used = r, cand; break
        else:
            fn = decs.get(base_type)
            if fn: dec_b, used = fn(cur), base_type
        if dec_b is None: return _err(ValueError(f"无法以{base_type}解码"), steps)
        steps.append(f"类型={used}")
        for _ in range(5):
            try: t = dec_b.decode("utf-8").strip()
            except UnicodeDecodeError: break
            nxt = None
            for name, fn in decs.items():
                if name == "base58": continue
                try:
                    r = fn(t)
                    if r and r.decode("utf-8"): nxt, used = r, name; break
                except Exception: pass
            if nxt is None: break
            dec_b = nxt; steps.append(f"嵌套:{used}")
        try: out = dec_b.decode("utf-8")
        except UnicodeDecodeError: out = dec_b.hex(); steps.append("非UTF-8转hex")
        return _ok(out, used, 0.9, steps=steps)
    except Exception as exc: return _err(exc, steps)
async def crypto_hex_decode(ciphertext: str) -> CryptoResult:
    """Hex解码。"""
    try:
        c = ciphertext.strip().replace(" ", "").replace("\n", "")
        if len(c) % 2 != 0: return _err(ValueError("Hex长度应为偶数"))
        d = binascii.unhexlify(c)
        try: out = d.decode("utf-8")
        except UnicodeDecodeError: out = d.decode("latin-1", errors="replace")
        return _ok(out, "hex", 0.95, steps=["Hex解码"])
    except Exception as exc: return _err(exc)
async def crypto_url_decode(ciphertext: str) -> CryptoResult:
    """URL解码。支持多层嵌套。"""
    steps: List[str] = []
    try:
        cur = ciphertext
        for i in range(5):
            d = urllib.parse.unquote(cur)
            if d == cur: break
            cur = d; steps.append(f"第{i+1}层解码")
        return _ok(cur, "url", 0.95, steps=steps or ["无需解码"])
    except Exception as exc: return _err(exc, steps)
async def crypto_morse_decode(ciphertext: str) -> CryptoResult:
    """摩斯电码解码。支持.和-或点和划。"""
    try:
        t = ciphertext.strip().replace("·", ".").replace("−", "-").replace("—", "-").replace("點", ".").replace("划", "-").replace("劃", "-").replace("|", " / ")
        words = []
        for wp in t.split(" / "):
            chars = [_MORSE.get(code.strip(), "?") for code in wp.split() if code.strip()]
            words.append("".join(chars))
        out = " ".join(words)
        return _ok(out, "morse", 0.9 if "?" not in out else 0.5, steps=["摩斯解码"])
    except Exception as exc: return _err(exc)
async def crypto_binary_decode(ciphertext: str) -> CryptoResult:
    """二进制解码(01101000->h)。支持空格分隔或连续, 自动补齐8位倍数。"""
    try:
        c = ciphertext.strip().replace(" ", "").replace("\n", "")
        if not re.fullmatch(r"[01]+", c): return _err(ValueError("含非二进制字符"))
        pad = (8 - len(c) % 8) % 8
        if pad: c = "0" * pad + c
        d = bytes(int(c[i:i+8], 2) for i in range(0, len(c), 8))
        try: out = d.decode("utf-8")
        except UnicodeDecodeError: out = d.decode("latin-1", errors="replace")
        return _ok(out, "binary", 0.95, steps=["二进制解码"])
    except Exception as exc: return _err(exc)
async def crypto_xor(ciphertext: Union[bytes, str], key: Union[bytes, str, int],
                     brute_force_key: bool = False) -> CryptoResult:
    """XOR解密。key为int时单字节XOR; 为bytes时重复密钥XOR。brute_force_key=True时自动爆破单字节key。"""
    steps: List[str] = []
    try:
        if isinstance(ciphertext, str):
            try: data = binascii.unhexlify(ciphertext.strip().replace(" ", "")); steps.append("hex解码为bytes")
            except Exception: data = ciphertext.encode("utf-8"); steps.append("UTF-8编码为bytes")
        else: data = ciphertext
        if not data: return _err(ValueError("密文为空"), steps)
        if brute_force_key:
            bs, bk, bp = -1e9, 0, b""
            for k in range(256):
                pt = bytes(b ^ k for b in data)
                try: sc = _score_en(pt.decode("utf-8"))
                except Exception: sc = _score_en(pt.decode("latin-1", errors="replace"))
                if sc > bs: bs, bk, bp = sc, k, pt
            steps.append(f"爆破key=0x{bk:02x},score={bs:.3f}")
            try: out = bp.decode("utf-8")
            except UnicodeDecodeError: out = bp.hex()
            return _ok(out, "xor_singlebyte", min(abs(bs) / max(len(out) * 0.03, 1), 1.0), f"0x{bk:02x}", steps)
        kb = bytes([key & 0xFF]) if isinstance(key, int) else (key.encode("utf-8") if isinstance(key, str) else key)
        pt = _xor(data, kb)
        try: out = pt.decode("utf-8")
        except UnicodeDecodeError: out = pt.hex(); steps.append("非UTF-8转hex")
        ks = key if isinstance(key, str) else (f"0x{key:02x}" if isinstance(key, int) else key.hex())
        return _ok(out, "xor", 0.8, ks, steps + [f"XOR key={ks}"])
    except Exception as exc: return _err(exc, steps)
# ─── 现代密码 ───
async def crypto_rsa_simple(n: int, e: int, c: int, p: int = None, q: int = None, d: int = None) -> CryptoResult:
    """RSA基础解密。提供p,q时计算d解密; 提供d直接解密。支持e=3低指数攻击(开立方根)。"""
    steps: List[str] = []
    try:
        if d is not None: steps.append(f"使用d={d}"); return _rsa_fmt(pow(c, d, n), steps, f"d={d}")
        if p is not None and q is not None:
            phi = (p - 1) * (q - 1); d_calc = pow(e, -1, phi); steps.append(f"p={p},q={q},d={d_calc}")
            return _rsa_fmt(pow(c, d_calc, n), steps, f"d={d_calc},p={p},q={q}")
        if e == 3:
            steps.append("e=3尝试立方根攻击"); m = round(c ** (1 / 3))
            for delta in range(-5, 6):
                if pow(m + delta, 3) == c: return _rsa_fmt(m + delta, steps, "low_exponent", "rsa_low_exponent")
            return _err(ValueError("立方根攻击未找到精确解"), steps)
        return _err(ValueError("缺少私钥参数"), steps)
    except Exception as exc: return _err(exc, steps)
async def crypto_rsa_common_modulus(n: int, e1: int, c1: int, e2: int, c2: int) -> CryptoResult:
    """RSA共模攻击。两个公钥共用n不同e时, 用扩展欧几里得求明文。"""
    steps: List[str] = []
    def _egcd(a, b):
        if b == 0: return a, 1, 0
        g, x1, y1 = _egcd(b, a % b); return g, y1, x1 - (a // b) * y1
    try:
        g, s, t = _egcd(e1, e2)
        if g != 1: return _err(ValueError(f"gcd(e1,e2)={g}!=1"), steps)
        if s < 0: c1, s = pow(c1, -1, n), -s
        if t < 0: c2, t = pow(c2, -1, n), -t
        m = (pow(c1, s, n) * pow(c2, t, n)) % n; steps.append(f"{s}*e1+{t}*e2=1")
        return _rsa_fmt(m, steps, f"s={s},t={t}", "rsa_common_modulus")
    except Exception as exc: return _err(exc, steps)
async def crypto_rsa_wiener(n: int, e: int) -> CryptoResult:
    """RSA Wiener攻击。d < n^0.25时用连分数分解n。返回(p, q, d)。"""
    steps: List[str] = []
    def _cf(a, b):
        while b: q = a // b; yield q; a, b = b, a - q * b
    def _conv(cf):
        p0, p1, q0, q1 = 0, 1, 1, 0
        for a in cf: pn, qn = a * p1 + p0, a * q1 + q0; yield pn, qn; p0, p1 = p1, pn; q0, q1 = q1, qn
    try:
        for k, dv in _conv(_cf(e, n)):
            if k == 0: continue
            if (e * dv - 1) % k != 0: continue
            phi = (e * dv - 1) // k; spq = n - phi + 1; disc = spq * spq - 4 * n
            if disc < 0: continue
            sd = int(math.isqrt(disc))
            if sd * sd != disc: continue
            p, q = (spq + sd) // 2, (spq - sd) // 2
            if p * q == n and p > 0 and q > 0: steps.append(f"收敛k/d={k}/{dv}"); return _ok(f"p={p}\nq={q}\nd={dv}", "rsa_wiener", 1.0, str(dv), steps)
        return _err(ValueError("Wiener攻击失败"), steps)
    except Exception as exc: return _err(exc, steps)
async def crypto_aes_decrypt(ciphertext: bytes, key: bytes, mode: str = "ECB", iv: bytes = None) -> CryptoResult:
    """AES解密。支持ECB/CBC模式。延迟加载Cryptodome。"""
    steps: List[str] = [f"AES-{mode},key={len(key)}B"]
    try:
        from Crypto.Cipher import AES  # type: ignore
        from Crypto.Util.Padding import unpad  # type: ignore
        m = mode.upper()
        if m == "ECB": cipher = AES.new(key, AES.MODE_ECB)
        elif m == "CBC": cipher = AES.new(key, AES.MODE_CBC, iv=iv or b"\x00" * 16)
        else: return _err(ValueError(f"不支持模式{mode}"), steps)
        pt = cipher.decrypt(ciphertext)
        try: pt = unpad(pt, AES.block_size)
        except Exception: pass
        try: out = pt.decode("utf-8")
        except UnicodeDecodeError: out = pt.hex()
        return _ok(out, f"aes-{m.lower()}", 1.0, steps=steps + ["成功"])
    except ImportError: return _err(ImportError("pip install pycryptodome"), steps)
    except Exception as exc: return _err(exc, steps)
async def crypto_des_decrypt(ciphertext: bytes, key: bytes) -> CryptoResult:
    """DES解密(ECB)。延迟加载Cryptodome。"""
    steps: List[str] = ["DES-ECB解密"]
    try:
        from Crypto.Cipher import DES  # type: ignore
        from Crypto.Util.Padding import unpad  # type: ignore
        pt = DES.new(key, DES.MODE_ECB).decrypt(ciphertext)
        try: pt = unpad(pt, DES.block_size)
        except Exception: pass
        try: out = pt.decode("utf-8")
        except UnicodeDecodeError: out = pt.hex()
        return _ok(out, "des-ecb", 1.0, steps=steps + ["成功"])
    except ImportError: return _err(ImportError("pip install pycryptodome"), steps)
    except Exception as exc: return _err(exc, steps)
# ─── 密码分析辅助 ───
async def crypto_frequency_analysis(ciphertext: str, top_n: int = 5) -> CryptoResult:
    """频率分析。返回最可能的替换映射(基于英文字频ETAOIN...)。"""
    try:
        letters = [c for c in ciphertext if c.isalpha()]
        if not letters: return _err(ValueError("输入不含字母"))
        freq = Counter(c.lower() for c in letters)
        se = [ch for ch, _ in sorted(_EN_FREQ.items(), key=lambda x: -x[1])]
        cc = [ch for ch, _ in freq.most_common()]
        mappings = []
        for i in range(min(top_n, 26)):
            mp = {cc[j]: se[(j + i) % 26] for j in range(len(cc)) if j < len(se)}
            pt = "".join(mp.get(c.lower(), c) if c.isalpha() else c for c in ciphertext)
            mappings.append((_score_en(pt), pt))
        mappings.sort(key=lambda x: -x[0])
        lines = [f"频率分析(密文频率前8:{dict(freq.most_common(8))})"] + [f"方案{idx}(sc={sc:.3f}):{pt[:200]}" for idx, (sc, pt) in enumerate(mappings[:top_n], 1)]
        return _ok("\n".join(lines), "frequency_analysis", 0.5, steps=["频率分析完成"], plaintext=mappings[0][1] if mappings else "")
    except Exception as exc: return _err(exc)
async def crypto_detect_encoding(ciphertext: str) -> CryptoResult:
    """自动检测编码类型。返回可能的编码列表及置信度。"""
    try:
        s = ciphertext.strip().replace(" ", "").replace("\n", "")
        r = []
        checks = [
            (lambda: re.fullmatch(r"[A-Za-z0-9+/=]+", s) and len(s) % 4 == 0 and len(s) >= 4, "base64", 0.90),
            (lambda: re.fullmatch(r"[A-Z2-7=]+", s.upper()) and len(s) % 8 in (0, 2, 4, 5, 7), "base32", 0.75),
            (lambda: re.fullmatch(r"[0-9a-fA-F]+", s) and len(s) % 2 == 0, "base16(hex)", 0.95),
            (lambda: re.fullmatch(r"[A-Za-z0-9!#$%&()*+-;<=>?@^_`{|}~]+", s), "base85", 0.50),
            (lambda: re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", s), "base58", 0.60),
            (lambda: "%" in s and bool(re.search(r"%[0-9A-Fa-f]{2}", s)), "url", 0.85),
            (lambda: re.fullmatch(r"[01]+", s) and len(s) >= 8, "binary", 0.80 if len(s) % 8 == 0 else 0.50),
            (lambda: re.fullmatch(r"[.\-·−\s/|]+", s) and ("-" in s or "." in s), "morse", 0.70),
        ]
        for check, name, conf in checks:
            if check(): r.append((name, conf))
        r.sort(key=lambda x: -x[1])
        out = "\n".join(f"{t}:{c}" for t, c in r) if r else "unknown:0.0"
        return _ok(out, "encoding_detection", r[0][1] if r else 0.0, steps=[f"检测到{len(r)}种可能"])
    except Exception as exc: return _err(exc)
async def crypto_hash_identify(hash_value: str) -> CryptoResult:
    """识别哈希类型。根据长度和特征判断MD5/SHA1/SHA256/NTLM等。"""
    try:
        h = hash_value.strip().lower(); r = []
        lm = {32: [("md5", 0.95), ("ntlm", 0.70)], 40: [("sha1", 0.95)], 56: [("sha224", 0.90)],
              64: [("sha256", 0.90)], 96: [("sha384", 0.90)], 128: [("sha512", 0.90)]}
        if len(h) in lm:
            for name, conf in lm[len(h)]: r.append((name, conf))
        if len(h) == 16: r.append(("mysql3", 0.80))
        if len(h) == 41 and h.startswith("*"): r.append(("mysql5", 0.90))
        if h.startswith("$2") and len(h) == 60: r.append(("bcrypt", 0.95))
        if len(h) == 8: r.append(("crc32", 0.50))
        if not r: r.append(("unknown", 0.0))
        r.sort(key=lambda x: -x[1])
        out = "\n".join(f"{t}:{c}" for t, c in r)
        return _ok(out, "hash_identify", r[0][1], steps=[f"长度={len(h)}"])
    except Exception as exc: return _err(exc)
async def crypto_brute_force(ciphertext: str, algorithm: str, wordlist: List[str] = None) -> CryptoResult:
    """暴力破解。algorithm为md5/sha1/sha256/rot/caesar/xor等。wordlist=None时使用内置字典。"""
    steps: List[str] = []
    try:
        targets = wordlist if wordlist is not None else _TOP50
        algo = algorithm.lower().strip(); steps.append(f"algo={algo},字典={len(targets)}")
        if algo in ("md5", "sha1", "sha256"):
            hf = getattr(hashlib, algo); tgt = ciphertext.strip().lower()
            for w in targets:
                if hf(w.encode()).hexdigest().lower() == tgt: return _ok(w, algo, 1.0, w, steps + [f"命中:{w}"])
            return _err(ValueError("字典未匹配"), steps)
        elif algo in ("rot", "caesar", "rot13"):
            tgt = ciphertext.lower()
            for w in targets:
                for sh in range(26):
                    if crypto_shift(w, sh).lower() == tgt: return _ok(w, "caesar", 1.0, str(sh), steps + [f"移位{sh}:{w}"])
            return _err(ValueError("未找到匹配"), steps)
        elif algo == "xor":
            data = binascii.unhexlify(ciphertext.strip().replace(" ", ""))
            for w in targets:
                pt = _xor(data, w.encode())
                try:
                    t = pt.decode("utf-8")
                    if all(32 <= ord(c) < 127 for c in t): return _ok(t, "xor", 1.0, w, steps + [f"XOR命中:{w}"])
                except Exception: pass
            return _err(ValueError("XOR字典未匹配"), steps)
        return _err(ValueError(f"不支持算法:{algo}"), steps)
    except Exception as exc: return _err(exc, steps)
# ─── 自动解题 ───
async def crypto_auto_solve(ciphertext: str, max_attempts: int = 50) -> CryptoResult:
    """自动尝试多种方法解题。依次尝试:编码检测/凯撒/ROT13/Atbash/XOR爆破/栅栏/维吉尼亚/频率分析。
    返回置信度最高的结果。"""
    steps: List[str] = [f"自动解题开始,输入长度={len(ciphertext)}"]
    results: List[Tuple[float, str, CryptoResult]] = []
    try:
        dr = await crypto_detect_encoding(ciphertext)
        if dr.success and dr.confidence > 0.7:
            em = {"base64": ("base64", crypto_base_decode), "base32": ("base32", crypto_base_decode),
                  "base16(hex)": ("base16", crypto_hex_decode), "url": ("url", crypto_url_decode),
                  "binary": ("binary", crypto_binary_decode), "morse": ("morse", crypto_morse_decode)}
            for line in dr.output.split("\n")[:3]:
                et = line.split(":")[0].strip()
                if et in em:
                    bt, fn = em[et]
                    r = await fn(ciphertext, bt) if "base" in et else await fn(ciphertext)
                    if r.success:
                        sc = _score_en(r.plaintext) if r.plaintext else 0
                        bonus = 1.5 if r.plaintext and " " in r.plaintext and all(c.isprintable() or c.isspace() for c in r.plaintext) else 0.5
                        results.append((sc + dr.confidence + bonus, f"编码-{et}", r)); steps.append(f"编码{et}:score={sc:.3f}+bonus={bonus:.1f}")
        for name, fn in [("caesar", crypto_caesar), ("rot13", crypto_rot13), ("atbash", crypto_atbash)]:
            r = await fn(ciphertext) if name != "caesar" else await crypto_caesar(ciphertext, True)
            if r.success:
                sc = _score_en(r.plaintext)
                bonus = 0.5 if r.plaintext and " " in r.plaintext and all(c.isprintable() or c.isspace() for c in r.plaintext) else 0
                results.append((sc + r.confidence + bonus, name, r)); steps.append(f"{name}:score={sc:.3f}+bonus={bonus:.1f}")
        xr = await crypto_xor(ciphertext, -1, brute_force_key=True)
        if xr.success: sc = _score_en(xr.plaintext); results.append((sc + xr.confidence, "xor", xr)); steps.append(f"XOR爆破:key={xr.key},score={sc:.3f}")
        rr = await crypto_railfence(ciphertext, True)
        if rr.success: sc = _score_en(rr.plaintext); results.append((sc + rr.confidence, "railfence", rr)); steps.append(f"栅栏:rails={rr.key},score={sc:.3f}")
        for kl in (3, 4):
            vr = await crypto_vigenere(ciphertext, key_length=kl)
            if vr.success:
                sc = _score_en(vr.plaintext)
                vconf = 0.3 if len(ciphertext) < 30 else 0.8
                results.append((sc + vconf, f"vigenere{kl}", vr)); steps.append(f"维吉尼亚(kl={kl}):key={vr.key},score={sc:.3f},conf={vconf}")
        fr = await crypto_frequency_analysis(ciphertext, top_n=1)
        if fr.success: sc = _score_en(fr.plaintext); results.append((sc + fr.confidence, "frequency", fr)); steps.append(f"频率分析:score={sc:.3f}")
        if not results: return _err(ValueError("所有方法均未成功"), steps)
        results.sort(key=lambda x: -x[0])
        best = results[0][2]
        best.steps = steps + [f"最佳方案:{results[0][1]}(综合评分={results[0][0]:.3f})"]
        return best
    except Exception as exc: return _err(exc, steps)
