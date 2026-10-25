from app.models.pack import FeaturePack


class JackYaoPack(FeaturePack):
    packId = "jack_yao"

    def pages(self):
        from .pages import CatalogPage
        return [CatalogPage]
