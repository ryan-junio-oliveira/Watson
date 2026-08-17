from ingestion.adapters.vision import VisionAnalyzer


class TestVisionParser:
    def test_parse_well_formed(self):
        result = VisionAnalyzer._parse(
            "CATEGORIA: diagram | DESCRICAO: diagrama do fluxo de papel"
        )
        assert result == {"category": "diagram", "description": "diagrama do fluxo de papel"}

    def test_parse_category_fallback(self):
        result = VisionAnalyzer._parse(
            "Essa imagem mostra um screenshot de uma tela de erro E123."
        )
        assert result is not None
        assert result["category"] == "screenshot"

    def test_parse_unparseable_returns_none(self):
        assert VisionAnalyzer._parse("não sei o que é isso") is None

    def test_analyze_unavailable_without_model(self):
        analyzer = VisionAnalyzer(model="")
        assert analyzer.available is False
        assert analyzer.analyze("/tmp/x.png") is None