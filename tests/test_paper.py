from printer_keystone.paper import mm_to_points


def test_mm_to_points():
    # 25.4mm == 1 inch == 72 points
    assert abs(mm_to_points(25.4) - 72.0) < 1e-9

