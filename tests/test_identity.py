from ingestion.identity import infer_identity


class TestInferIdentity:
    def test_hp_model(self):
        manufacturer, model = infer_identity("HP_E52645_Service_Manual.pdf")
        assert manufacturer == "HP"
        assert "E52645" in model

    def test_brother(self):
        manufacturer, model = infer_identity("Brother_MFC-7860DW_Troubleshooting.pdf")
        assert manufacturer == "BROTHER"
        assert "MFC-7860DW" in model

    def test_no_manufacturer(self):
        manufacturer, model = infer_identity("manual_geral_v2.pdf")
        assert manufacturer == ""
        assert model in ("", "v2")

    def test_plain_name(self):
        manufacturer, model = infer_identity("relatorio.xlsx")
        assert manufacturer == ""
        assert model == ""

    def test_xerox_series_word_not_model(self):
        manufacturer, model = infer_identity("Xerox_Manual_Series.docx")
        assert manufacturer == "XEROX"