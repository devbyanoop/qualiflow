import uuid

from qualiflow_agents.evidence import sha256_hex, store_evidence, verify_evidence

ORG_ID = "test-org"
FEATURE_ID = "evidence-tests"


# --- Positive ---------------------------------------------------------------


def test_positive_store_and_verify_round_trip():
    """Real MinIO calls, no mocking. Stores real artifacts, then
    verify_evidence independently re-fetches and re-hashes them --
    this is the actual thing M0.10 is supposed to prove."""
    case_review_id = str(uuid.uuid4())
    manifest = store_evidence(ORG_ID, FEATURE_ID, case_review_id, "print('hi')", "1 passed", True)

    assert manifest["script_sha256"] == sha256_hex("print('hi')")
    assert manifest["output_sha256"] == sha256_hex("1 passed")
    assert verify_evidence(manifest) is True


def test_positive_stored_objects_are_independently_fetchable():
    """Don't just trust verify_evidence's own math -- directly list the
    bucket and confirm all three objects genuinely exist at the keys
    the manifest claims, the way an auditor with only S3 credentials
    and no QualiFlow code would check."""
    from qualiflow_agents.evidence import BUCKET, _s3

    case_review_id = str(uuid.uuid4())
    manifest = store_evidence(ORG_ID, FEATURE_ID, case_review_id, "code-x", "output-y", False)

    listing = _s3.list_objects_v2(Bucket=BUCKET, Prefix=f"{ORG_ID}/{FEATURE_ID}/{case_review_id}")
    keys = {obj["Key"] for obj in listing.get("Contents", [])}
    assert keys == {manifest["script_key"], manifest["output_key"], manifest["manifest_key"]}


# --- Negative -----------------------------------------------------------


def test_negative_verify_evidence_rejects_tampered_hash():
    """If the manifest's recorded hash doesn't match what's actually
    stored -- whether through corruption or tampering -- verify_evidence
    must say so, not silently pass."""
    case_review_id = str(uuid.uuid4())
    manifest = store_evidence(ORG_ID, FEATURE_ID, case_review_id, "real code", "real output", True)

    tampered = dict(manifest)
    tampered["script_sha256"] = sha256_hex("different code entirely")
    assert verify_evidence(tampered) is False


# --- Edge ------------------------------------------------------------------


def test_edge_empty_code_and_output_still_hash_and_verify():
    """A dry run could in principle produce empty output (e.g. a script
    that was never executed). Must not crash on empty strings."""
    case_review_id = str(uuid.uuid4())
    manifest = store_evidence(ORG_ID, FEATURE_ID, case_review_id, "", "", False)

    assert manifest["script_sha256"] == sha256_hex("")
    assert verify_evidence(manifest) is True


def test_edge_ensure_bucket_is_idempotent_when_bucket_already_exists():
    """_ensure_bucket runs on every store_evidence call -- calling it
    repeatedly against a bucket that already exists must not raise."""
    from qualiflow_agents.evidence import _ensure_bucket

    _ensure_bucket()
    _ensure_bucket()  # must not raise on the second call


# --- Regression --------------------------------------------------------------
#
# This whole project has repeatedly hit Windows-specific path bugs
# (the ProactorEventLoop saga). S3 keys must always use forward
# slashes regardless of host OS -- guard against ever building them
# with os.path.join, which would silently emit backslashes on Windows
# and break every downstream S3/MinIO lookup.


def test_regression_manifest_keys_never_contain_backslashes():
    case_review_id = str(uuid.uuid4())
    manifest = store_evidence(ORG_ID, FEATURE_ID, case_review_id, "code", "output", True)

    for key_name in ("script_key", "output_key", "manifest_key"):
        assert "\\" not in manifest[key_name], f"{key_name} must use forward slashes: {manifest[key_name]!r}"
