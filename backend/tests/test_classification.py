from app.services.classification import classify_component


def test_classify_bearing_as_buy():
    assert classify_component("Bearing", "Deep groove ball bearing", 0.9) == "Buy"


def test_classify_shaft_as_make():
    assert classify_component("Shaft", "Custom machined shaft", 0.9) == "Make"


def test_classify_low_confidence_always_review():
    assert classify_component("Bearing", "Bearing", 0.1) == "Review"


def test_classify_unknown_category_as_review():
    assert classify_component("Widget", "Unidentified widget thing", 0.9) == "Review"
