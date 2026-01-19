import pytest
from pentestagent.workspaces.validation import gather_candidate_targets, is_target_in_scope

def test_gather_candidate_targets_shallow():
    args = {
        "target": "10.0.0.1",
        "hosts": ["host1", "host2"],
        "nested": {"target": "should_not_find"},
        "ip": "192.168.1.1",
        "irrelevant": "nope"
    }
    result = gather_candidate_targets(args)
    assert "10.0.0.1" in result
    assert "host1" in result and "host2" in result
    assert "192.168.1.1" in result
    assert "should_not_find" not in result
    assert "nope" not in result

def test_is_target_in_scope_ip_cidr_hostname():
    allowed = ["192.168.0.0/16", "host.local", "10.0.0.1"]
    # IP in CIDR
    assert is_target_in_scope("192.168.1.5", allowed)
    # Exact IP
    assert is_target_in_scope("10.0.0.1", allowed)
    # Hostname
    assert is_target_in_scope("host.local", allowed)
    # Not in scope
    assert not is_target_in_scope("8.8.8.8", allowed)
    assert not is_target_in_scope("otherhost", allowed)

def test_is_target_in_scope_cidr_vs_cidr():
    allowed = ["10.0.0.0/24"]
    # Subnet of allowed
    assert is_target_in_scope("10.0.0.128/25", allowed)
    # Same network
    assert is_target_in_scope("10.0.0.0/24", allowed)
    # Not a subnet
    assert not is_target_in_scope("10.0.1.0/24", allowed)

def test_is_target_in_scope_single_ip_cidr():
    allowed = ["10.0.0.1"]
    # Single-IP network
    assert is_target_in_scope("10.0.0.1/32", allowed)
    # Not matching
    assert not is_target_in_scope("10.0.0.2/32", allowed)

def test_is_target_in_scope_case_insensitive_hostname():
    allowed = ["Example.COM"]
    assert is_target_in_scope("example.com", allowed)
    assert is_target_in_scope("EXAMPLE.com", allowed)
    assert not is_target_in_scope("other.com", allowed)
