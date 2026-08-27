from core.domain.value_objects.qc_report import QCReport, QCDecision, QCMetric, DetectedDefect

def test_qc_report_serialization():
    metric1 = QCMetric(name="identity_score", score=0.95, threshold=0.90, passed=True)
    metric2 = QCMetric(name="temporal_score", score=0.60, threshold=0.80, passed=False)
    defect = DetectedDefect(description="left eye changes shape", frame_range=[48, 71], severity="high")

    report = QCReport(
        decision=QCDecision.REPAIR_SEGMENT,
        metrics=[metric1, metric2],
        defects=[defect]
    )

    data = report.to_dict()
    assert data["decision"] == "REPAIR_SEGMENT"

    restored = QCReport.from_dict(data)
    assert restored.decision == QCDecision.REPAIR_SEGMENT
    assert len(restored.metrics) == 2
    assert restored.metrics[0].name == "identity_score"
    assert len(restored.defects) == 1
    assert restored.defects[0].description == "left eye changes shape"
