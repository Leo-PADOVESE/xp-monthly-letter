from core.letter_ai import check_attention_points, check_numbers, check_promises, check_scope, tidy


def letter(text: str) -> dict:
    return {"opening_pt": text}


def test_promises_are_flagged_even_when_hedged():
    found = check_promises(letter("Investir agora pode melhorar a rentabilidade e potencialmente aumentar os ganhos."))
    assert found == ["aumentar os ganhos", "melhorar a rentabilidade"]


def test_conditional_macro_and_fgc_are_not_promises():
    text = ("O cenário da XP tende a favorecer a renda fixa pós-fixada. O CDB é garantido pelo FGC "
            "e a movimentação reduz a concentração da carteira.")
    assert check_promises(letter(text)) == []


def test_numbers_match_by_value():
    assert check_numbers(letter("A carteira rendeu +3,95%, acima de 15%."), {"r": "+3,95%", "l": "15,00%"}) == []
    assert check_numbers(letter("Rendeu 4,10%."), {"r": "+3,95%"}) == ["4,10%"]


def test_tidy_removes_repeated_greeting():
    out = tidy({"performance_pt": ["Caro Bruno, em abril sua carteira caiu.", "Segundo parágrafo."]})
    assert out["performance_pt"] == ["Em abril sua carteira caiu.", "Segundo parágrafo."]


def test_attention_points_must_cite_a_portfolio_fact():
    facts = {"facts": [{"id": "idle_cash"}, {"id": "class_weights"}]}
    assert check_attention_points({"attention_points": [{"fact_id": "idle_cash"}]}, facts) == []
    bad = {"attention_points": [{"fact_id": "buy_petr4"}, {"fact_id": "idle_cash"}, {"fact_id": "idle_cash"}]}
    assert check_attention_points(bad, facts) == ["ponto de atenção sem fato da carteira: buy_petr4",
                                                  "fato repetido: idle_cash"]


def test_month_and_window_figures_stay_in_their_paragraphs():
    results = {"formatted": {"portfolio_return": "+3,95%", "cdi": "+1,06%"},
               "consolidated_window": {"portfolio": "+7,61%", "cdi": "+11,45%"}}
    ok = {"performance_pt": ["No mês, +3,95% contra +1,06% do CDI."],
          "consolidated_pt": "Nos últimos 12 meses, +7,61% contra +11,45% do CDI."}
    assert check_scope(ok, results) == []
    mixed = {"performance_pt": ["No mês, +7,61%."], "consolidated_pt": "Em 12 meses, +3,95%."}
    assert len(check_scope(mixed, results)) == 2
    assert check_scope(mixed, {"formatted": results["formatted"]}) == []   # no window, nothing to mix
