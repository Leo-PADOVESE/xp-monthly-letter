import json
from datetime import date

import pytest

from core import market_data


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "CACHE_DIR", tmp_path)
    return tmp_path


def test_inflation_uses_ipca15_of_the_period_month(cache):
    rows = [{"data": "01/04/2025", "valor": "0.43"}]
    (cache / "sgs_7478_2025-04-01_2025-04-30.json").write_text(json.dumps(rows))
    # April's full IPCA is only published on May 9, after the May 7 letter; IPCA-15 is known.
    assert market_data.ipca_for_period(date(2025, 3, 31), date(2025, 4, 30)) == pytest.approx(0.0043)


def test_cdi_compounds_daily_rates_excluding_the_end_date(cache):
    rows = [{"data": "07/04/2025", "valor": "0.05"}, {"data": "08/04/2025", "valor": "0.05"},
            {"data": "09/04/2025", "valor": "0.05"}]
    (cache / "sgs_12_2025-04-07_2025-04-09.json").write_text(json.dumps(rows))
    assert market_data.cdi_return(date(2025, 4, 7), date(2025, 4, 9)) == pytest.approx(1.0005 ** 2 - 1)
