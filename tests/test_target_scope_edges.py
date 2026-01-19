from pentestagent.workspaces import validation
from pentestagent.workspaces.manager import TargetManager


def test_ip_in_cidr_containment():
    allowed = ["10.0.0.0/8"]
    assert validation.is_target_in_scope("10.1.2.3", allowed)


def test_cidr_within_cidr():
    allowed = ["10.0.0.0/8"]
    assert validation.is_target_in_scope("10.1.0.0/16", allowed)


def test_cidr_equal_allowed():
    allowed = ["10.0.0.0/8"]
    assert validation.is_target_in_scope("10.0.0.0/8", allowed)


def test_cidr_larger_than_allowed_is_out_of_scope():
    allowed = ["10.0.0.0/24"]
    assert not validation.is_target_in_scope("10.0.0.0/16", allowed)


def test_single_ip_vs_single_address_cidr():
    allowed = ["192.168.1.5"]
    # Candidate expressed as a /32 network should be allowed when it represents the same single address
    assert validation.is_target_in_scope("192.168.1.5/32", allowed)


def test_hostname_case_insensitive_match():
    allowed = ["example.com"]
    assert validation.is_target_in_scope("Example.COM", allowed)


def test_hostname_vs_ip_not_match():
    allowed = ["example.com"]
    assert not validation.is_target_in_scope("93.184.216.34", allowed)


def test_gather_candidate_targets_shallow_behavior():
    # shallow extraction: list of strings is extracted
    args = {"targets": ["1.2.3.4", "example.com"]}
    assert set(validation.gather_candidate_targets(args)) == {"1.2.3.4", "example.com"}

    # nested dicts inside lists are NOT traversed by the shallow extractor
    args2 = {"hosts": [{"ip": "5.6.7.8"}]}
    assert validation.gather_candidate_targets(args2) == []

    # direct string argument returns itself
    assert validation.gather_candidate_targets("8.8.8.8") == ["8.8.8.8"]


def test_normalize_target_accepts_hostnames_and_ips():
    assert TargetManager.normalize_target("example.com") == "example.com"
    assert TargetManager.normalize_target("8.8.8.8") == "8.8.8.8"
