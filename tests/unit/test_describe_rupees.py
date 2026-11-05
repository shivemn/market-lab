from marketlab.describe import rupees


def test_rupees_use_indian_grouping() -> None:
    assert rupees(0) == "₹0.00"
    assert rupees(5) == "₹0.05"
    assert rupees(99_999) == "₹999.99"
    assert rupees(100_000) == "₹1,000.00"
    assert rupees(10_000_000) == "₹1,00,000.00"
    assert rupees(1_234_567_890) == "₹1,23,45,678.90"
    assert rupees(-25_029_686) == "-₹2,50,296.86"
