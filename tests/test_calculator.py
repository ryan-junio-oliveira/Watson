from rag.calculator import Calculator, NumberExtractor, format_number, parse_number


class TestParseNumber:
    def test_simple_int(self):
        assert parse_number("15") == 15.0

    def test_comma_decimal(self):
        assert parse_number("15,5") == 15.5

    def test_thousands_separator(self):
        assert parse_number("1.500") == 1500.0

    def test_combined(self):
        assert parse_number("1.234,56") == 1234.56

    def test_invalid(self):
        assert parse_number("abc") is None


class TestFormatNumber:
    def test_ptbr_format(self):
        assert format_number(33.33) == "33,33"
        assert format_number(1000) == "1.000"
        assert format_number(17.5) == "17,5"


class TestCalculator:
    def setup_method(self):
        self.calc = Calculator()

    def test_percent_change_between_months(self):
        texts = ["agosto: 15 impressões", "setembro: 20 impressões"]
        result = self.calc.compute_for_question(
            "quantos % a mais de impressão em setembro?", texts
        )
        assert result is not None
        assert result.kind == "percent_change"
        assert result.result == pytest.approx(33.3333, rel=1e-3)
        assert "33,33%" in result.prompt_block()
        assert "Agosto" in result.prompt_block()
        assert "Setembro" in result.prompt_block()

    def test_percent_change_negative(self):
        texts = ["janeiro: 40", "fevereiro: 30"]
        result = self.calc.compute_for_question("quantos % a menos em fevereiro?", texts)
        assert result is not None
        assert result.result == pytest.approx(-25.0)
        assert "25%" in result.prompt_block()

    def test_sum(self):
        texts = ["agosto: 15", "setembro: 20"]
        result = self.calc.compute_for_question("qual a soma total?", texts)
        assert result is not None
        assert result.kind == "sum"
        assert result.result == 35.0

    def test_average(self):
        texts = ["agosto: 15", "setembro: 20"]
        result = self.calc.compute_for_question("qual a média?", texts)
        assert result is not None
        assert result.kind == "average"
        assert result.result == 17.5

    def test_max(self):
        texts = ["agosto: 15", "setembro: 20"]
        result = self.calc.compute_for_question("qual mês teve mais impressões?", texts)
        assert result is not None
        assert result.kind == "max"
        assert result.result == 20.0

    def test_min(self):
        texts = ["agosto: 15", "setembro: 20"]
        result = self.calc.compute_for_question("qual mês teve menos?", texts)
        assert result is not None
        assert result.kind == "min"
        assert result.result == 15.0

    def test_difference(self):
        texts = ["agosto: 15", "setembro: 20"]
        result = self.calc.compute_for_question("qual a diferença?", texts)
        assert result is not None
        assert result.kind == "difference"
        assert result.result == 5.0

    def test_no_intent_returns_none(self):
        texts = ["agosto: 15", "setembro: 20"]
        assert self.calc.compute_for_question("qual a capital do Brasil?", texts) is None

    def test_insufficient_facts_returns_none(self):
        texts = ["agosto: 15"]
        assert (
            self.calc.compute_for_question("quantos % a mais?", texts) is None
        )

    def test_db_row_format(self):
        texts = [
            "[Tabela: print_jobs] mes: agosto | total: 15",
            "[Tabela: print_jobs] mes: setembro | total: 20",
        ]
        result = self.calc.compute_for_question(
            "quantos % a mais em setembro comparado a agosto?", texts
        )
        assert result is not None
        assert result.kind == "percent_change"
        assert result.result == pytest.approx(33.3333, rel=1e-3)


class TestNumberExtractor:
    def test_extract_key_value(self):
        facts = NumberExtractor().extract(["impressões: 15", "contador: 20"])
        values = sorted(f.value for f in facts)
        assert values == [15.0, 20.0]

    def test_ignores_noisy_keys(self):
        facts = NumberExtractor().extract(["id: 5", "page: 3", "impressões: 10"])
        values = [f.value for f in facts]
        assert 10.0 in values
        assert 5.0 not in values
        assert 3.0 not in values


import pytest  # noqa: E402
