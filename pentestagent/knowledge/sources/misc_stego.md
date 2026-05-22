# 隐写与取证

## 原理
隐写题的本质是把信息埋进另一个看似正常的载体里，并尽量不破坏载体表面的可用性与自然性。对 CTF 来说，载体可能是图像、音频、视频、PDF、Office、压缩包、二进制文件、二维码、网络流量甚至文件系统时间戳。真正困难的通常不是“知道有哪些工具”，而是先判断隐藏发生在哪一层：文件尾追加、容器嵌套、LSB、调色板、Alpha 通道、频域、元数据、结构字段、协议分片、时间侧信道，还是多层编码叠加。处理这类题的正确起点通常是低噪声的被动检查：确认文件类型与魔数、大小与维度、元数据、字符串、熵分布、容器结构、通道差异、网络协议方向与时间序列，再决定是否上专用提取工具。

隐写与流量取证题常常刻意制造“假线索过多”的局面：例如 PNG 里既有注释又有尾部附加数据，PCAP 中既有 DNS beacon 又有 HTTP 下载，音频里既有频谱文字又有 LSB。为了避免在工具海里乱撞，应坚持一条原则：先证明哪一层发生了异常，再继续向下挖。图像题先看文件尾部、IHDR/IDAT/PLTE/alpha 结构与像素统计；音频题先看采样率、声道、频谱与可视化；PCAP 题先按协议、会话、时间轴和数据方向做拆分；文档题先看对象结构、修订记录、隐藏层、注释和嵌入附件。这样才能快速从“可疑现象”收敛到“可复现提取链”。

## 工具与命令示例
```bash
# 1) 识别真实文件类型与基础信息
file sample.png

# 2) 提取元数据，适合图片、PDF、Office、音视频
exiftool sample.jpg

# 3) 检查 PNG 结构与 chunk 异常
pngcheck -v sample.png

# 4) 搜索可打印字符串，适合尾部追加、明文提示、协议残留
strings -n 6 sample.bin

# 5) 自动提取嵌套文件，常用于图片后拼接 zip/rar
binwalk -e sample.png

# 6) 检查 PNG/BMP 的最低有效位隐写
zsteg sample.png

# 7) 提取 steghide 隐藏内容（若题目确实用到该格式）
steghide extract -sf sample.jpg

# 8) 分析流量概况与时间轴
tshark -r traffic.pcap -q -z io,stat,1

# 9) 按协议导出 HTTP 对象
tshark -r traffic.pcap --export-objects http,http_out

# 10) 列出 DNS 查询，观察是否有可疑分段数据
 tshark -r traffic.pcap -Y dns -T fields -e dns.qry.name
```

## 常见 CTF 题型
### 题型一：PNG/BMP 的 LSB 隐写
思路：图像显示正常，但最低有效位被拿来存储 bit 流。优先用 `zsteg`、像素通道可视化与行列模式检查，确认数据藏在 RGB 还是 Alpha、按行还是按列、是否做了 base64/压缩。

```python
from PIL import Image
img = Image.open('sample.png').convert('RGBA')
bits = []
for y in range(img.height):
    for x in range(img.width):
        r, g, b, a = img.getpixel((x, y))
        bits.append(str(r & 1))
out = ''.join(chr(int(''.join(bits[i:i+8]), 2)) for i in range(0, len(bits), 8))
print(out[:200])
```

### 题型二：文件尾追加或容器嵌套
思路：图片、PDF、音频尾部拼接 ZIP/RAR/7z 是高频基础题。先看 `file` 与 `binwalk` 输出，再手工检查尾部签名，必要时 carve 出附加文件。

```python
data = open('sample.png','rb').read()
pos = data.find(b'PK\x03\x04')
if pos != -1:
    open('carved.zip','wb').write(data[pos:])
    print('zip at', pos)
```

### 题型三：PCAP 中协议分片外带
思路：流量题常把 flag 拆成 DNS 子域、HTTP 参数、ICMP 负载、WebSocket 帧或固定长度 beacon。先按协议分组与时间轴定位异常，再重组字段并解码。

```python
import base64
parts = []
for line in open('dns.txt', encoding='utf-8'):
    sub = line.strip().split('.')[0]
    parts.append(sub)
raw = ''.join(parts)
print(base64.b32decode(raw.upper()))
```

### 题型四：音频频谱与隐藏声道
思路：音频题不一定靠 LSB，更常见的是把二维码、文本、摩斯、DTMF 画进频谱，或把数据藏在某个声道。先看波形与频谱，再考虑单独导出左右声道和降速播放。

```bash
ffmpeg -i sample.wav -map_channel 0.0.0 left.wav -map_channel 0.0.1 right.wav
```

## 绕过与进阶技巧
- **先做容器识别**：题目扩展名不可信，始终先用 `file`、魔数和结构工具确认真实格式。
- **图像先看通道差异**：RGB、Alpha、调色板、位平面可分别可视化，很多隐藏不会出现在肉眼可见层。
- **多层编码常叠加**：提取出的数据可能还要再过 base64、hex、xor、gzip、二维码、压缩包密码等处理，不要提到一半停下。
- **PCAP 不要只盯 HTTP**：DNS、ICMP、TLS SNI、WebSocket、SMB、FTP、USB 抓包都可能是载体。
- **时间也是信道**：固定间隔、包长序列、TTL、查询顺序、文件时间戳都可能编码信息。
- **文档类题看修订与对象**：PDF 注释、对象流、XMP，Office 批注、隐藏工作表、修订记录、嵌入文件都值得检查。
- **对比样本价值高**：若给了多张近似图片、多个几乎相同的文件，做差分通常能迅速显露异常区域。
- **不要迷信大工具**：工具跑不出结果不代表没有隐藏，很多题恰恰要求你手工按结构字段重组数据。
- **记住题目目标**：有的题只是让你定位隐藏位置，有的要求完整恢复原文或解压出第二层附件，验证链路要闭环。

## 快速检查清单
- [ ] 真实文件类型、魔数、尺寸、编码参数是否已确认
- [ ] 是否检查了元数据、注释、修订记录、嵌入对象与文件尾附加数据
- [ ] 图像是否已看过位平面、Alpha、调色板、单通道差异
- [ ] 是否用 `binwalk`、`strings`、结构工具排查了容器嵌套
- [ ] 音频是否检查过频谱、左右声道、降速与静音段
- [ ] PCAP 是否按协议、时间轴、数据方向与会话做了拆分
- [ ] 提取出的内容是否继续检查了 base64、hex、xor、压缩等第二层编码
- [ ] 是否存在多份相似样本，可通过差分定位异常
- [ ] 是否已排除“假线索”，只围绕已证实异常的那一层深挖
- [ ] 最终提取结果是否已验证为可读文本、文件或 flag 格式
