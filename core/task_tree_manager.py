"""Task Tree Manager for PTT-based autonomous agent mode."""

import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from enum import Enum


class NodeStatus(Enum):
    """Enumeration of possible node statuses."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    VULNERABLE = "vulnerable"
    NOT_VULNERABLE = "not_vulnerable"


class RiskLevel(Enum):
    """Enumeration of risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskNode:
    """Represents a single node in the task tree."""
    
    def __init__(
        self,
        description: str,
        parent_id: Optional[str] = None,
        node_type: str = "task",
        **kwargs
    ):
        """Initialize a task node."""
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.description = description
        self.status = NodeStatus(kwargs.get('status', NodeStatus.PENDING.value))
        self.node_type = node_type  # task, phase, finding, objective
        self.parent_id = parent_id
        self.children_ids: List[str] = kwargs.get('children_ids', [])
        
        # Task execution details
        self.tool_used = kwargs.get('tool_used', None)
        self.command_executed = kwargs.get('command_executed', None)
        self.output_summary = kwargs.get('output_summary', None)
        self.findings = kwargs.get('findings', None)
        
        # Metadata
        self.priority = kwargs.get('priority', 5)  # 1-10, higher is more important
        self.risk_level = RiskLevel(kwargs.get('risk_level', RiskLevel.LOW.value))
        self.timestamp = kwargs.get('timestamp', None)
        self.kb_references = kwargs.get('kb_references', [])
        self.dependencies = kwargs.get('dependencies', [])
        
        # Additional attributes
        self.attributes = kwargs.get('attributes', {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary representation."""
        return {
            'id': self.id,
            'description': self.description,
            'status': self.status.value,
            'node_type': self.node_type,
            'parent_id': self.parent_id,
            'children_ids': self.children_ids,
            'tool_used': self.tool_used,
            'command_executed': self.command_executed,
            'output_summary': self.output_summary,
            'findings': self.findings,
            'priority': self.priority,
            'risk_level': self.risk_level.value,
            'timestamp': self.timestamp,
            'kb_references': self.kb_references,
            'dependencies': self.dependencies,
            'attributes': self.attributes
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskNode':
        """Create node from dictionary representation."""
        return cls(
            description=data['description'],
            **data
        )


class TaskTreeManager:
    """Manages the Pentesting Task Tree (PTT) structure and operations."""
    
    def __init__(self):
        """Initialize the task tree manager."""
        self.nodes: Dict[str, TaskNode] = {}
        self.root_id: Optional[str] = None
        self.goal: Optional[str] = None
        self.target: Optional[str] = None
        self.constraints: Dict[str, Any] = {}
        self.creation_time = datetime.now()
        
    def initialize_tree(self, goal: str, target: str, constraints: Dict[str, Any] = None) -> str:
        """
        Initialize the task tree with a goal and target.
        
        Args:
            goal: The primary objective
            target: The target system/network
            constraints: Any constraints or scope limitations
            
        Returns:
            The root node ID
        """
        self.goal = goal
        self.target = target
        self.constraints = constraints or {}
        
        # Create root node - let the LLM determine what structure is needed
        root_node = TaskNode(
            description=f"Goal: {goal}",
            node_type="objective"
        )
        self.root_id = root_node.id
        self.nodes[root_node.id] = root_node
        
        return self.root_id
    
    def add_node(self, node: TaskNode) -> str:
        """
        Add a node to the tree.
        
        Args:
            node: The TaskNode to add
            
        Returns:
            The node ID
        """
        self.nodes[node.id] = node
        
        # Update parent's children list
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node.id not in parent.children_ids:
                parent.children_ids.append(node.id)
        
        return node.id
    
    def update_node(self, node_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update a node's attributes.
        
        Args:
            node_id: The ID of the node to update
            updates: Dictionary of attributes to update
            
        Returns:
            True if successful, False otherwise
        """
        if node_id not in self.nodes:
            return False
        
        node = self.nodes[node_id]
        
        # Update allowed fields
        allowed_fields = {
            'status', 'tool_used', 'command_executed', 'output_summary',
            'findings', 'priority', 'risk_level', 'timestamp', 'kb_references'
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                if field == 'status':
                    node.status = NodeStatus(value)
                elif field == 'risk_level':
                    node.risk_level = RiskLevel(value)
                else:
                    setattr(node, field, value)
            elif field == 'attributes':
                node.attributes.update(value)
        
        return True
    
    def get_node(self, node_id: str) -> Optional[TaskNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_children(self, node_id: str) -> List[TaskNode]:
        """Get all children of a node."""
        if node_id not in self.nodes:
            return []
        
        parent = self.nodes[node_id]
        return [self.nodes[child_id] for child_id in parent.children_ids if child_id in self.nodes]
    
    def get_leaf_nodes(self) -> List[TaskNode]:
        """Get all leaf nodes (nodes without children)."""
        return [node for node in self.nodes.values() if not node.children_ids]
    
    def get_candidate_tasks(self) -> List[TaskNode]:
        """
        Get candidate tasks for next action.
        
        Returns tasks that are:
        - Leaf nodes
        - Status is PENDING or FAILED
        - All dependencies are completed
        """
        candidates = []
        
        for node in self.get_leaf_nodes():
            if node.status in [NodeStatus.PENDING, NodeStatus.FAILED]:
                # Check dependencies
                deps_satisfied = all(
                    self.nodes.get(dep_id, TaskNode("")).status == NodeStatus.COMPLETED
                    for dep_id in node.dependencies
                )
                
                if deps_satisfied:
                    candidates.append(node)
        
        return candidates
    
    def prioritize_tasks(self, tasks: List[TaskNode]) -> List[TaskNode]:
        """
        Prioritize tasks based on various factors.
        
        Args:
            tasks: List of candidate tasks
            
        Returns:
            Sorted list of tasks (highest priority first)
        """
        def task_score(task: TaskNode) -> float:
            # Base score from priority
            score = task.priority
            
            # Boost for reconnaissance tasks in early stages
            if "recon" in task.description.lower() or "scan" in task.description.lower():
                completed_count = sum(1 for n in self.nodes.values() if n.status == NodeStatus.COMPLETED)
                if completed_count < 5:
                    score += 3
            
            # Boost for vulnerability assessment after recon
            if "vuln" in task.description.lower() and self._has_completed_recon():
                score += 2
            
            # Penalty for high-risk tasks early on
            if task.risk_level == RiskLevel.HIGH:
                score -= 2
            
            return score
        
        return sorted(tasks, key=task_score, reverse=True)
    
    def _has_completed_recon(self) -> bool:
        """Check if basic reconnaissance has been completed."""
        recon_keywords = ["scan", "recon", "enumerat", "discover"]
        completed_recon = any(
            any(keyword in node.description.lower() for keyword in recon_keywords)
            and node.status == NodeStatus.COMPLETED
            for node in self.nodes.values()
        )
        return completed_recon
    
    def to_natural_language(self, node_id: Optional[str] = None, indent: int = 0) -> str:
        """
        Convert the tree (or subtree) to natural language representation.
        
        Args:
            node_id: Starting node ID (None for root)
            indent: Indentation level
            
        Returns:
            Natural language representation of the tree
        """
        if node_id is None:
            node_id = self.root_id
        
        if node_id not in self.nodes:
            return ""
        
        node = self.nodes[node_id]
        indent_str = "  " * indent
        
        # Format node information
        status_symbol = {
            NodeStatus.PENDING: "○",
            NodeStatus.IN_PROGRESS: "◐",
            NodeStatus.COMPLETED: "●",
            NodeStatus.FAILED: "✗",
            NodeStatus.BLOCKED: "□",
            NodeStatus.VULNERABLE: "⚠",
            NodeStatus.NOT_VULNERABLE: "✓"
        }.get(node.status, "?")
        
        lines = [f"{indent_str}{status_symbol} {node.description}"]
        
        # Add findings if present
        if node.findings:
            lines.append(f"{indent_str}  → Findings: {node.findings}")
        
        # Add tool/command info if present
        if node.tool_used:
            lines.append(f"{indent_str}  → Tool: {node.tool_used}")
        
        # Process children
        for child_id in node.children_ids:
            lines.append(self.to_natural_language(child_id, indent + 1))
        
        return "\n".join(lines)
    
    def to_json(self) -> str:
        """Serialize the tree to JSON."""
        data = {
            'goal': self.goal,
            'target': self.target,
            'constraints': self.constraints,
            'root_id': self.root_id,
            'creation_time': self.creation_time.isoformat(),
            'nodes': {node_id: node.to_dict() for node_id, node in self.nodes.items()}
        }
        return json.dumps(data, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'TaskTreeManager':
        """Deserialize a tree from JSON."""
        data = json.loads(json_str)
        
        manager = cls()
        manager.goal = data['goal']
        manager.target = data['target']
        manager.constraints = data['constraints']
        manager.root_id = data['root_id']
        manager.creation_time = datetime.fromisoformat(data['creation_time'])
        
        # Recreate nodes
        for node_id, node_data in data['nodes'].items():
            node = TaskNode.from_dict(node_data)
            manager.nodes[node_id] = node
        
        return manager
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tree statistics."""
        status_counts = {}
        for node in self.nodes.values():
            status = node.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            'total_nodes': len(self.nodes),
            'status_counts': status_counts,
            'leaf_nodes': len(self.get_leaf_nodes()),
            'candidate_tasks': len(self.get_candidate_tasks())
        } 