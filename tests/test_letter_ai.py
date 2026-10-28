from core.letter_ai import check_numbers, check_promises, tidy


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
