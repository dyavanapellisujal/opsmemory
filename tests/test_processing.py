"""Tests for the knowledge processing pipeline (parsers, chunker, relationships)."""

from opsmemory.domain.enums import DocumentSource
from opsmemory.processing.chunker import chunk_document
from opsmemory.processing.models import NormalizedDocument, RawContent
from opsmemory.processing.parsers import parse
from opsmemory.processing.relationships import extract_relationships, extract_technologies


def test_parse_markdown_extracts_title() -> None:
    raw = RawContent(
        identifier="docs/runbook-redis.md",
        content="# Redis Recovery\n\nRotate the secret.",
        content_type="markdown",
    )
    doc = parse(raw, DocumentSource.LOCAL_FILES)
    assert doc.title == "Redis Recovery"
    assert "runbook" in doc.tags
    assert doc.source is DocumentSource.LOCAL_FILES


def test_parse_html_strips_nav_and_converts() -> None:
    raw = RawContent(
        identifier="https://docs.example.com/deploy",
        content=(
            "<html><head><title>Deploy Guide</title></head><body>"
            "<nav>menu</nav><h1>Deploying</h1><p>Use helm.</p>"
            "<script>alert(1)</script></body></html>"
        ),
        content_type="html",
        url="https://docs.example.com/deploy",
    )
    doc = parse(raw, DocumentSource.HTTP_DOCS)
    assert doc.title == "Deploying"
    assert "Use helm" in doc.content
    assert "menu" not in doc.content
    assert "alert" not in doc.content


def test_parse_yaml_kubernetes_manifest() -> None:
    raw = RawContent(
        identifier="k8s/deployment.yaml",
        content="apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: payments-api\n",
        content_type="yaml",
    )
    doc = parse(raw, DocumentSource.LOCAL_FILES)
    assert doc.title == "payments-api"
    assert "```yaml" in doc.content


def test_parse_invalid_json_falls_back_to_raw() -> None:
    raw = RawContent(identifier="broken.json", content="{not json", content_type="json")
    doc = parse(raw, DocumentSource.LOCAL_FILES)
    assert doc.content == "{not json"


def test_chunker_splits_on_headings_with_hierarchy() -> None:
    content = (
        "intro paragraph that is long enough to stand alone as a chunk\n\n"
        "# Deployment\nUse helm to deploy the service to the cluster.\n\n"
        "## Rollback\nRun helm rollback with the previous revision number.\n\n"
        "# Monitoring\nDashboards live in Grafana under the payments folder."
    )
    chunks = chunk_document(content, title="payments-api")
    sections = [c.section for c in chunks]
    assert "payments-api" in sections[0]
    assert "Deployment" in sections
    assert "Deployment > Rollback" in sections
    assert [c.position for c in chunks] == list(range(len(chunks)))


def test_chunker_merges_tiny_fragments() -> None:
    content = "# A\nA longer section with plenty of content to keep around.\n\n# B\nok"
    chunks = chunk_document(content)
    assert len(chunks) == 1  # the tiny trailing section is merged into its predecessor
    assert "# B" in chunks[0].content


def test_relationships_depends_on_and_service_mentions() -> None:
    doc = NormalizedDocument(
        identifier="readme.md",
        title="payments-api README",
        content="payments-api depends on redis for caching. The orders-api uses it too.",
        source=DocumentSource.LOCAL_FILES,
    )
    rels = extract_relationships(doc, known_services=["orders-api"])
    triples = {(r.source_name, r.relation, r.target_name) for r in rels}
    assert ("payments-api", "depends_on", "redis") in triples
    assert ("orders-api", "documented_by", "payments-api README") in triples


def test_extract_technologies() -> None:
    assert extract_technologies("We use Redis and Kafka on Kubernetes") == [
        "redis",
        "kafka",
        "kubernetes",
    ]
