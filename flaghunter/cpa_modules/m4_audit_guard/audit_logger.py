"""
FlagHunter M4 Audit Guard — 不可篡改的操作审计日志系统
核心特性: sha256哈希链防篡改, JSON Lines格式, 多类型审计记录,
会话级摘要与风险评级, 完整性校验, ZIP证据包导出, 日志归档
技术约束: Python 3.10+, 仅标准库, 零外部依赖
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import hashlib, json, os, shutil, uuid, zipfile


# ── 数据模型 ──────────────────────────────

@dataclass
class AuditEntry:
    """单条审计记录

    Attributes:
        timestamp: UTC时间戳; entry_id: 唯一ID(UUID); session_id: 所属会话ID
        action_type: 动作类型 command|tool|llm_request|llm_response|file_access|network|flag_submit|blocked
        action_detail: 操作详情字典; target: 操作目标(IP/域名/文件路径)
        user: 操作用户; source_ip: 源IP; result: success|failure|blocked|pending
        duration_ms: 执行耗时(毫秒); hash_chain: sha256(上一条hash + 当前内容JSON)
    """
    timestamp: datetime
    entry_id: str
    session_id: str
    action_type: str
    action_detail: dict
    target: str = ""
    user: str = "default"
    source_ip: str = ""
    result: str = ""
    duration_ms: int = 0
    hash_chain: str = ""

    def to_dict(self) -> dict:
        """转为可JSON序列化的字典，datetime转ISO格式"""
        d = asdict(self)
        if isinstance(d["timestamp"], datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """从字典还原，timestamp支持ISO字符串(含Z后缀)"""
        ts = data.get("timestamp", "")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return cls(timestamp=ts if isinstance(ts, datetime) else datetime.utcnow(),
                   entry_id=data.get("entry_id", ""), session_id=data.get("session_id", ""),
                   action_type=data.get("action_type", ""), action_detail=data.get("action_detail", {}),
                   target=data.get("target", ""), user=data.get("user", "default"),
                   source_ip=data.get("source_ip", ""), result=data.get("result", ""),
                   duration_ms=data.get("duration_ms", 0), hash_chain=data.get("hash_chain", ""))


@dataclass
class AuditSummary:
    """审计摘要 — 按会话聚合统计"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    total_commands: int = 0
    total_tools: int = 0
    total_llm_requests: int = 0
    total_findings: int = 0
    blocked_actions: int = 0
    targets_accessed: List[str] = field(default_factory=list)
    risk_level: str = "low"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("start_time", "end_time"):
            if isinstance(d[k], datetime):
                d[k] = d[k].isoformat()
        return d


# ── 核心审计日志管理器 ──────────────────────

class AuditLogger:
    """审计日志管理器 — 不可篡改的操作留痕系统

    基于sha256哈希链实现日志防篡改。每条新记录将前一条记录的hash_chain
    值纳入本记录哈希计算形成链式结构。某条记录被修改后其hash_chain将与
    后续记录不匹配，校验时可立即发现。
    """

    def __init__(self, log_dir: str = "./logs/audit", retention_days: int = 90):
        """初始化审计日志管理器

        Args:
            log_dir: 日志文件存储根目录; retention_days: 日志保留天数(超期归档)
        """
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._archive_dir = self._log_dir / "archive"
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._current_file: Optional[Path] = None
        self._last_hash: str = "0" * 64
        self._load_last_hash()

    # ── 内部工具 ──────────────────────────────

    def _get_current_logfile(self) -> Path:
        """返回当前日期日志文件路径 log_dir/audit_YYYYMMDD.jsonl"""
        return self._log_dir / f"audit_{datetime.utcnow().strftime('%Y%m%d')}.jsonl"

    def _load_last_hash(self) -> None:
        """从当前日志文件最后一条读取hash_chain，更新self._last_hash"""
        current = self._get_current_logfile()
        if not current.exists():
            self._last_hash = "0" * 64
            return
        try:
            with open(current, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                self._last_hash = "0" * 64
                return
            self._last_hash = json.loads(lines[-1].strip()).get("hash_chain", "0" * 64)
        except (json.JSONDecodeError, OSError, KeyError):
            self._last_hash = "0" * 64

    def _compute_hash(self, previous_hash: str, entry_data: str) -> str:
        """计算哈希链值: sha256(previous_hash + entry_data)，返回64位hex字符串"""
        return hashlib.sha256((previous_hash + entry_data).encode("utf-8")).hexdigest()

    def _get_all_logfiles(self) -> List[Path]:
        """获取所有未归档的.jsonl日志文件列表，按文件名排序"""
        return sorted(self._log_dir.glob("audit_*.jsonl"))

    # ── 核心记录 ──────────────────────────────

    def log(self, entry: AuditEntry) -> str:
        """写入单条审计记录：计算hash_chain → 追加写入JSONL → flush → 只读 → 更新last_hash

        Args:
            entry: 待写入的AuditEntry实例

        Returns:
            entry.entry_id
        """
        self._current_file = self._get_current_logfile()
        entry.timestamp = datetime.utcnow()
        if not entry.entry_id:
            entry.entry_id = str(uuid.uuid4())
        # 构造用于哈希的JSON(不含hash_chain字段本身)
        hash_payload = entry.to_dict()
        hash_payload.pop("hash_chain", None)
        entry_json = json.dumps(hash_payload, ensure_ascii=False, sort_keys=True)
        entry.hash_chain = self._compute_hash(self._last_hash, entry_json)
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        # 写入前确保可写，完成后设为只读
        try:
            os.chmod(self._current_file, 0o644)
        except (OSError, NotImplementedError):
            pass
        with open(self._current_file, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(self._current_file, 0o444)
        except (OSError, NotImplementedError):
            pass
        self._last_hash = entry.hash_chain
        return entry.entry_id

    def log_command(self, command: str, target: str = "", exit_code: int = None,
                    output_preview: str = "", session_id: str = "") -> str:
        """便捷方法: 记录命令执行(含退出码和输出预览)"""
        detail = {"command": command, "exit_code": exit_code, "output_preview": output_preview[:500]}
        result = "success" if exit_code == 0 else "failure" if exit_code is not None else "pending"
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="command", action_detail=detail,
                                   target=target, result=result))

    def log_tool(self, tool_name: str, args: dict, target: str = "",
                 finding: str = "", session_id: str = "") -> str:
        """便捷方法: 记录工具调用(含发现结果)"""
        detail = {"tool_name": tool_name, "args": args, "finding": finding}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="tool", action_detail=detail,
                                   target=target, result="success" if finding else "pending"))

    def log_llm_request(self, model: str, prompt_tokens: int, messages_preview: str,
                        provider_id: str = "", session_id: str = "") -> str:
        """便捷方法: 记录LLM请求(含token数和消息预览)"""
        detail = {"model": model, "prompt_tokens": prompt_tokens,
                  "messages_preview": messages_preview[:500], "provider_id": provider_id}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="llm_request", action_detail=detail,
                                   result="pending"))

    def log_llm_response(self, model: str, completion_tokens: int, response_preview: str,
                         provider_id: str = "", session_id: str = "") -> str:
        """便捷方法: 记录LLM响应(含输出token和响应预览)"""
        detail = {"model": model, "completion_tokens": completion_tokens,
                  "response_preview": response_preview[:500], "provider_id": provider_id}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="llm_response", action_detail=detail,
                                   result="success"))

    def log_file_access(self, file_path: str, operation: str = "read",
                        session_id: str = "") -> str:
        """便捷方法: 记录文件访问(operation: read|write|delete|list)"""
        detail = {"file_path": file_path, "operation": operation}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="file_access", action_detail=detail,
                                   target=file_path, result="success"))

    def log_network(self, dest_ip: str, dest_port: int, protocol: str = "tcp",
                    session_id: str = "") -> str:
        """便捷方法: 记录网络操作(目标IP/端口/协议)"""
        detail = {"dest_ip": dest_ip, "dest_port": dest_port, "protocol": protocol}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="network", action_detail=detail,
                                   target=f"{dest_ip}:{dest_port}/{protocol}", result="success"))

    def log_flag_submit(self, flag: str, platform: str, challenge_id: str = "",
                        correct: bool = False, session_id: str = "") -> str:
        """便捷方法: 记录Flag提交(Flag自动脱敏为flag{***})"""
        masked = "flag{***}" if flag.startswith("flag{") else "***"
        detail = {"flag": masked, "platform": platform, "challenge_id": challenge_id, "correct": correct}
        return self.log(AuditEntry(timestamp=datetime.utcnow(), entry_id=str(uuid.uuid4()),
                                   session_id=session_id, action_type="flag_submit", action_detail=detail,
                                   target=platform, result="success" if correct else "failure"))

    # ── 查询 ──────────────────────────────────

    def query(self, session_id: str = None, action_type: str = None, target: str = None,
              start_time: datetime = None, end_time: datetime = None, limit: int = 100) -> List[AuditEntry]:
        """多条件查询审计日志(AND关系)，从后往前读取(最近优先)，达到limit停止

        所有过滤条件均为可选。
        """
        results: List[AuditEntry] = []
        for logfile in reversed(self._get_all_logfiles()):
            with open(logfile, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = AuditEntry.from_dict(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if session_id and entry.session_id != session_id:
                    continue
                if action_type and entry.action_type != action_type:
                    continue
                if target and target.lower() not in entry.target.lower():
                    continue
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                results.append(entry)
                if len(results) >= limit:
                    return results
        return results

    def query_by_session(self, session_id: str) -> List[AuditEntry]:
        """查询指定会话的全部审计记录(按时间倒序)"""
        return self.query(session_id=session_id, limit=10000)

    def get_session_summary(self, session_id: str) -> AuditSummary:
        """获取会话级审计摘要与风险评级

        统计commands/tools/llm_requests/blocked_actions数量，
        blocked_actions决定risk_level: 0=low 2=medium 5=high 10=critical。
        """
        entries = self.query_by_session(session_id)
        if not entries:
            return AuditSummary(session_id=session_id, start_time=datetime.utcnow(),
                                end_time=datetime.utcnow())
        summary = AuditSummary(session_id=session_id, start_time=entries[-1].timestamp,
                               end_time=entries[0].timestamp)
        targets = set()
        for e in entries:
            if e.action_type == "command":
                summary.total_commands += 1
            elif e.action_type == "tool":
                summary.total_tools += 1
                if e.action_detail.get("finding"):
                    summary.total_findings += 1
            elif e.action_type == "llm_request":
                summary.total_llm_requests += 1
            elif e.action_type == "blocked":
                summary.blocked_actions += 1
            if e.target:
                targets.add(e.target)
        summary.targets_accessed = sorted(targets)
        ba = summary.blocked_actions
        summary.risk_level = "critical" if ba >= 10 else "high" if ba >= 5 else "medium" if ba >= 2 else "low"
        return summary

    def get_recent(self, n: int = 50) -> List[AuditEntry]:
        """获取最近N条审计记录(从最新日志文件末尾读，不足向前回溯)"""
        results: List[AuditEntry] = []
        for logfile in reversed(self._get_all_logfiles()):
            with open(logfile, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        results.append(AuditEntry.from_dict(json.loads(line)))
                    except json.JSONDecodeError:
                        continue
                    if len(results) >= n:
                        return results[:n]
        return results

    # ── 完整性验证 ────────────────────────────

    def verify_chain(self, date: str = None) -> tuple:
        """验证指定日期的哈希链完整性，逐条重新计算hash_chain与存储值对比

        Args:
            date: 日期字符串YYYYMMDD，None表示当天

        Returns:
            (valid: bool, first_broken_id: str|None)
        """
        if date is None:
            date = datetime.utcnow().strftime("%Y%m%d")
        logfile = self._log_dir / f"audit_{date}.jsonl"
        if not logfile.exists():
            return (True, None)
        previous_hash = "0" * 64
        with open(logfile, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    return (False, "json_decode_error")
                entry = AuditEntry.from_dict(data)
                hash_payload = entry.to_dict()
                hash_payload.pop("hash_chain", None)
                computed = self._compute_hash(previous_hash, json.dumps(hash_payload, ensure_ascii=False, sort_keys=True))
                if computed != data.get("hash_chain", ""):
                    return (False, entry.entry_id)
                previous_hash = data["hash_chain"]
        return (True, None)

    def verify_all(self) -> dict:
        """验证所有日志文件的哈希链完整性

        Returns:
            {filename: {"valid": bool, "first_broken": str}}
        """
        results = {}
        for logfile in self._get_all_logfiles():
            valid, broken = self.verify_chain(logfile.stem.replace("audit_", ""))
            results[logfile.name] = {"valid": valid, "first_broken": broken}
        return results

    # ── 导出 ──────────────────────────────────

    def export_session(self, session_id: str, output_path: str) -> str:
        """导出指定会话的审计日志为JSON文件(含日志列表与完整性验证报告)

        Returns:
            实际导出的文件路径
        """
        entries = self.query_by_session(session_id)
        export_data = {
            "session_id": session_id,
            "exported_at": datetime.utcnow().isoformat(),
            "total_entries": len(entries),
            "entries": [e.to_dict() for e in entries],
            "verify_report": self.verify_all(),
        }
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return str(out)

    def export_evidence_package(self, session_id: str, output_path: str) -> str:
        """导出ZIP格式证据包，包含: audit.json + verify_report.json + summary.json + timeline.html

        Returns:
            实际导出的ZIP文件路径
        """
        entries = self.query_by_session(session_id)
        verify_report = self.verify_all()
        summary = self.get_session_summary(session_id)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("audit.json", json.dumps([e.to_dict() for e in entries], ensure_ascii=False, indent=2))
            zf.writestr("verify_report.json", json.dumps(verify_report, ensure_ascii=False, indent=2))
            zf.writestr("summary.json", json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
            zf.writestr("timeline.html", self._build_timeline_html(session_id, entries))
        return str(out)

    def _build_timeline_html(self, session_id: str, entries: List[AuditEntry]) -> str:
        """构建时间线HTML页面(紧凑内联样式)"""
        css = "body{font-family:'Segoe UI',Arial,sans-serif;margin:40px;background:#f5f6fa;color:#2c3e50}h1{font-size:24px;margin-bottom:20px}.s{background:#fff;padding:16px 20px;border-radius:8px;margin-bottom:24px;box-shadow:0 2px 4px rgba(0,0,0,0.06)}.e{background:#fff;padding:14px 20px;border-radius:6px;margin-bottom:10px;border-left:4px solid #3498db;box-shadow:0 1px 3px rgba(0,0,0,0.04)}.e.b{border-left-color:#e74c3c}.e.c{border-left-color:#2ecc71}.e.t{border-left-color:#f39c12}.e.f{border-left-color:#9b59b6}.ts{color:#7f8c8d;font-size:12px}.at{font-weight:bold;color:#2980b9}.tg{color:#27ae60}.r{font-size:12px;padding:2px 8px;border-radius:4px;display:inline-block;margin-left:8px}.rs{background:#d4edda;color:#155724}.rf{background:#f8d7da;color:#721c24}.rb{background:#fff3cd;color:#856404}"
        items = []
        for e in entries:
            c = {"command": "c", "tool": "t", "blocked": "b", "flag_submit": "f"}.get(e.action_type, "")
            rc = e.result if e.result in ("success", "failure", "blocked") else ""
            ds = json.dumps(e.action_detail, ensure_ascii=False)[:200]
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            tg = f'<span class="tg">目标:{e.target}</span>' if e.target else ""
            rc_letter = rc[:1]  # 空字符串或首字母
            items.append(f'<div class="e {c}"><span class="ts">{ts}</span> <span class="at">[{e.action_type}]</span> <span class="r r{rc_letter}">{e.result}</span> {tg}<div>详情:{ds}</div></div>')
        return f"<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><title>审计时间线-{session_id}</title><style>{css}</style></head><body><h1>审计时间线—会话{session_id}</h1><div class=\"s\"><strong>总记录数:</strong>{len(entries)}<br><strong>导出时间:</strong>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}UTC</div>{''.join(items)}</body></html>"

    # ── 维护 ──────────────────────────────────

    def archive_old_logs(self) -> int:
        """将超过留存期的.jsonl日志归档到archive/目录，返回归档文件数量"""
        cutoff = datetime.utcnow() - timedelta(days=self._retention_days)
        count = 0
        for logfile in self._log_dir.glob("audit_*.jsonl"):
            try:
                mtime = datetime.utcfromtimestamp(logfile.stat().st_mtime)
            except OSError:
                continue
            if mtime < cutoff:
                shutil.move(str(logfile), str(self._archive_dir / logfile.name))
                count += 1
        return count
