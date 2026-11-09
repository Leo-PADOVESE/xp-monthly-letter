"""A full CVM month (hundreds of thousands of rows) is read once and only the funds asked for stay in memory."""

from datetime import date

import pandas as pd

from core import market_data


def test_full_month_read_once(tmp_path, monkeypatch):
    rows = [{"CNPJ": f"{i:014d}", "DT_COMPTC": f"2025-04-{d:02d}", "VL_QUOTA": "1.0"}
            for i in range(30_000) for d in (29, 30)]
    rows += [{"CNPJ": "43917493000131", "DT_COMPTC": "2025-04-30", "VL_QUOTA": "2.5"}]
    pd.DataFrame(rows).to_csv(tmp_path / "cvm_inf_diario_202504.csv", index=False)
    pd.DataFrame(rows[:2]).to_csv(tmp_path / "cvm_inf_diario_202503.csv", index=False)
    monkeypatch.setattr(market_data, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(market_data, "_CVM_FRAMES", {})
    reads = []
    load = market_data._load_cvm_daily_report
    monkeypatch.setattr(market_data, "_load_cvm_daily_report", lambda m: reads.append(m) or load(m))

    for _ in range(5):
        assert market_data.fund_quota_point("43.917.493/0001-31", date(2025, 4, 30)) == (date(2025, 4, 30), 2.5)
    assert reads.count("202504") == 1
    assert len(market_data._CVM_FRAMES["202504"]) < 100                  # not the 60 thousand rows
    assert not market_data.fund_has_quotas("99.999.999/9999-99", date(2025, 4, 30))
    assert not market_data.fund_has_quotas("99.999.999/9999-99", date(2025, 4, 30))
    assert reads.count("202504") == 2                                     # a new fund reads the month once more
