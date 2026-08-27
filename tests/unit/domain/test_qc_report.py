from core.domain.value_objects.qc_report import QCReport

def test_qc_report_serialization():
    report = QCReport(
        decision="REPAIR",
        metrics={"identity_score": 0.95, "temporal_score": 0.60},
        defects=["left eye changes shape"]
    )

    data = report.to_dict()
    assert data["decision"] == "REPAIR"

    restored = QCReport.from_dict(data)
    assert restored.decision == "REPAIR"
    assert restored.metrics["identity_score"] == 0.95
    assert "left eye changes shape" in restored.defects
