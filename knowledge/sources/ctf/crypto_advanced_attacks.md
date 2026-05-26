# Advanced Cryptographic Attacks for CTF

> Beyond basic RSA and classical ciphers — covering ECC, lattice-based crypto, LFSR, block cipher attacks, and hash exploitation.

---

## 1. ECC (Elliptic Curve Cryptography) Attacks

### 1.1 Basic ECC Parameters
- Curve equation: `y² = x³ + ax + b (mod p)`
- Generator point `G`, order `n`
- Private key `d`, public key `Q = d * G`

### 1.2 Smart's Attack (Anomalous Curve)

When curve order `#E(Fp) == p` (anomalous curve), the ECDLP reduces to the additive group.

```python
# sage
E = EllipticCurve(GF(p), [a, b])
assert E.order() == p  # Anomalous
P = E.point(Px, Py)
Q = E.point(Qx, Qy)
d = P.log(Q)  # Directly solvable
```

### 1.3 Singular Curve Attack

When discriminant `Δ = 4a³ + 27b² ≡ 0 (mod p)`, the curve is singular.

**Case A: Node** (`c1 ≠ c2`)
- Map to multiplicative group: `φ(P) = (y - c1*x)/(y - c2*x)`
- Solve DLP in `Fp*`

**Case B: Cusp** (`c1 == c2`)
- Map to additive group: `φ(P) = x/y`
- Solve DLP in `Fp+`

```python
# sage
E = EllipticCurve(GF(p), [a, b])
assert E.discriminant() == 0
# Find singular point
f = x^3 + a*x + b
f.factor()  # Find repeated root → singular point
```

### 1.4 MOV Attack (Supersingular Curves)

For supersingular curves, ECDLP can be reduced to DLP in `Fp^k*` where embedding degree `k` is small (typically `k ≤ 6`).

```python
# sage
E = EllipticCurve(GF(p), [a, b])
k = E.embedding_degree()  # If small, MOV applies
```

### 1.5 Small Subgroup Confinement

If the curve has a small cofactor `h`, forcing scalar multiplication into a small subgroup allows brute force.

```python
# sage
# If curve order = h * n where h is small
P = h * G  # Point in subgroup of order n
# If h is small, h*P might have small order
```

### 1.6 ECDSA Nonce Reuse

If the same nonce `k` is used for two signatures:

```
s1 = k⁻¹ * (h1 + r * d) mod n
s2 = k⁻¹ * (h2 + r * d) mod n
→ k = (h1 - h2) / (s1 - s2) mod n
→ d = (s1 * k - h1) / r mod n
```

Python:
```python
from Crypto.Util.number import inverse

k = ((h1 - h2) * inverse(s1 - s2, n)) % n
d = ((s1 * k - h1) * inverse(r, n)) % n
```

### 1.7 ECDSA Biased Nonce (Lattice Attack)

If nonce `k` is partially known or biased (e.g., lower bits are zero):
- Use LLL / BKZ lattice reduction to recover private key
- Tool: `sage` with `Lattice Reduction`

---

## 2. Lattice-Based Attacks

### 2.1 LLL (Lenstra-Lenstra-Lovász) Algorithm

Reduces a lattice basis to find short vectors.

```python
# sage
M = Matrix(ZZ, [[...], [...]])  # Lattice basis
B = M.LLL()
short_vector = B[0]
```

### 2.2 Coppersmith's Method

Find small roots of polynomial equations modulo N.

**Application**: RSA partial key exposure, stereotyped messages.

```python
# sage
N = ...  # RSA modulus
P.<x> = Zmod(N)[]
f = x + known_part  # f(x) = x + known_high_bits
roots = f.small_roots(X=2^unknown_bits, beta=0.5)
```

### 2.3 Wiener's Attack (via LLL)

When private exponent `d < N^0.25 / 3`:

```python
# sage or owiener
import owiener
d = owiener.attack(e, n)
```

### 2.4 Franklin-Reiter Related Message Attack

When two messages satisfy a known polynomial relation:

```python
# sage
# m2 = f(m1) where f is known (e.g., m2 = m1 + delta)
P.<m> = PolynomialRing(Zmod(n))
g1 = m^e - c1
g2 = (m + delta)^e - c2
# GCD of polynomials
m = -composite_modulus_gcd(g1, g2).coefficients()[0]
```

### 2.5 Hastad's Broadcast Attack (CRT)

Same message encrypted with same small `e` to multiple moduli:

```python
from Crypto.Util.number import long_to_bytes
import gmpy2

# e=3, three ciphertexts with three moduli
c = CRT([c1, c2, c3], [n1, n2, n3])
m = int(gmpy2.iroot(c, 3)[0])
print(long_to_bytes(m))
```

### 2.6 Boneh-Durfee Attack

When `d < N^0.292`:

```python
# sage
# Implementation: https://github.com/mimoo/RSA-and-LLL-attacks
```

---

## 3. LFSR (Linear Feedback Shift Register) Attacks

### 3.1 Berlekamp-Massey Algorithm

Given output sequence, find shortest LFSR that generates it.

```python
from sage.matrix.berlekamp_massey import berlekamp_massey

seq = [1, 0, 1, 1, 0, ...]
poly = berlekamp_massey(seq)  # Connection polynomial
```

### 3.2 Known Plaintext Attack

If keystream = ciphertext XOR plaintext:
```python
keystream = [c ^ p for c, p in zip(ciphertext, known_plaintext)]
poly = berlekamp_massey(keystream)
# Recover LFSR state and predict future keystream
```

### 3.3 Walsh-Hadamard Transform

For nonlinear-filtered LFSR, use correlation attacks.

---

## 4. Block Cipher Attacks

### 4.1 AES Key Recovery from Partial Information

**S-box differential**: If you can control plaintext and observe ciphertext with error oracle.

### 4.2 Bit-Flipping Attack (CBC Mode)

```
Ciphertext: C0 || C1 || C2 || ...
Flip byte in C1 → corresponding byte in P2 is flipped!
```

**Exploit**: Tamper with cookie/permission fields.

```python
def cbc_bitflip(ciphertext, block_size, target_pos, old_byte, new_byte):
    c = bytearray(ciphertext)
    # target_pos is in plaintext block i
    # flip corresponding byte in ciphertext block i-1
    cipher_pos = target_pos - (target_pos % block_size) - block_size + (target_pos % block_size)
    c[cipher_pos] ^= old_byte ^ new_byte
    return bytes(c)
```

### 4.3 Padding Oracle Attack (CBC Mode)

When server leaks padding validity:

```python
# Tool: padbuster or custom script
# For each byte position, brute force until valid padding
# Recover plaintext byte-by-byte
```

### 4.4 ECB Cut-and-Paste

Same plaintext block → same ciphertext block.
- Can rearrange/replay blocks
- Can detect block boundaries

### 4.5 DES Weak Keys

```python
# DES weak keys produce identical subkeys
weak_keys = [
    bytes.fromhex("0101010101010101"),
    bytes.fromhex("FEFEFEFEFEFEFEFE"),
    bytes.fromhex("E0E0E0E0F1F1F1F1"),
    bytes.fromhex("1F1F1F1F0E0E0E0E"),
]
# Encryption with weak key = decryption with same key
```

---

## 5. Hash Function Attacks

### 5.1 Length Extension Attack

For Merkle-Damgård hashes (MD5, SHA1, SHA256):

If you know `Hash(secret || message)`, you can compute `Hash(secret || message || padding || extension)` without knowing `secret`.

```python
from hashpumpy import hashpump

new_hash, new_message = hashpump(
    original_hash,
    original_message,
    extension,
    key_length
)
```

### 5.2 Hash Collision

**MD5**: Practical collision generation via `hashclash`.
```bash
# https://github.com/cr-marcstevens/hashclash
```

**SHA1**: SHAttered attack (theoretical, CTF sometimes uses known prefix collision).

### 5.3 HMAC Extension

If you know `HMAC(key, message)` and the key length, sometimes you can forge.

---

## 6. Common CTF Crypto Patterns

| Challenge Type | Recognition | Attack |
|---------------|-------------|--------|
| RSA with `e=3` and small `m` | `c = m³ mod n`, `m³ < n` | Cube root |
| RSA with partial `p` | Leaked high/low bits of `p` | Coppersmith |
| RSA with related messages | `m2 = m1 + k` | Franklin-Reiter |
| ECC singular curve | `4a³ + 27b² ≡ 0` | Map to Fp* or Fp+ |
| ECC anomalous | `#E == p` | Smart's attack |
| LFSR output | Binary sequence | Berlekamp-Massey |
| CBC padding oracle | Different error for bad padding | Padding oracle |
| CBC bit flip | Cookie/userdata in CBC | Bit-flipping |
| Length extension | `Hash(secret\|\|msg)` format | hashpump |
| Partial nonce ECDSA | Biased `k` | Lattice attack |

---

## 7. SageMath Crypto Cheat Sheet

```python
# Factorization
factor(n)

# Discrete log
discrete_log(mod(c, p), mod(g, p))

# Modular square root
mod(c, p).sqrt()

# Polynomial ring
R.<x> = Zmod(n)[]
f = x^2 + a*x + b
roots = f.roots()

# LLL
M = Matrix(ZZ, [[...]])
B = M.LLL()

# ECC
E = EllipticCurve(GF(p), [a, b])
P = E.random_point()
Q = d * P  # Scalar multiplication

# Integer relations (find small x_i such that sum(x_i * a_i) = 0)
pari.lindep([a1, a2, a3])
```
