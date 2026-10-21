import hashlib
import json
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from .settings import settings

BUCKET = "qualiflow-evidence"

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.minio_endpoint_url,
    aws_access_key_id=settings.minio_root_user,
    aws_secret_access_key=settings.minio_root_password,
)


def _ensure_bucket() -> None:
    try:
        _s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        _s3.create_bucket(Bucket=BUCKET)


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def store_evidence(org_id: str, feature_id: str, case_review_id: str, code: str, output: str, passed: bool) -> dict:
    """A toy version of the plan's §12.1 evidence package — notice
    everything deliberately missing: no WORM storage, no hash-chaining
    across runs, no trusted timestamps, no e-signatures (that's Phase
    4's compliance pack). This proves just the mechanism: hash the
    real artifacts, write a manifest alongside them in S3-compatible
    object storage, so someone could in principle verify the hash
    without touching QualiFlow at all."""
    _ensure_bucket()

    script_hash = sha256_hex(code)
    output_hash = sha256_hex(output)
    timestamp = datetime.now(timezone.utc).isoformat()

    prefix = f"{org_id}/{feature_id}/{case_review_id}"
    script_key = f"{prefix}/script.py"
    output_key = f"{prefix}/output.txt"
    manifest_key = f"{prefix}/manifest.json"

    manifest = {
        "org_id": org_id,
        "feature_id": feature_id,
        "case_review_id": case_review_id,
        "timestamp": timestamp,
        "passed": passed,
        "script_sha256": script_hash,
        "output_sha256": output_hash,
        "script_key": script_key,
        "output_key": output_key,
        "manifest_key": manifest_key,
    }

    _s3.put_object(Bucket=BUCKET, Key=script_key, Body=code.encode("utf-8"))
    _s3.put_object(Bucket=BUCKET, Key=output_key, Body=output.encode("utf-8"))
    _s3.put_object(Bucket=BUCKET, Key=manifest_key, Body=json.dumps(manifest, indent=2).encode("utf-8"))

    return manifest


def verify_evidence(manifest: dict) -> bool:
    """The actual proof this milestone asks for: fetch the stored
    artifacts back and recompute their hashes independently, without
    assuming store_evidence's own math was right. If this returns
    True, the manifest's hashes genuinely match what's stored — the
    same check anyone with S3 credentials and no QualiFlow code could
    run themselves."""
    script_obj = _s3.get_object(Bucket=BUCKET, Key=manifest["script_key"])
    output_obj = _s3.get_object(Bucket=BUCKET, Key=manifest["output_key"])
    stored_code = script_obj["Body"].read().decode("utf-8")
    stored_output = output_obj["Body"].read().decode("utf-8")

    return (
        sha256_hex(stored_code) == manifest["script_sha256"]
        and sha256_hex(stored_output) == manifest["output_sha256"]
    )
