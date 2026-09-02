from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.core.cache import cache
        from django.db.models.signals import post_delete, post_save

        from .models import Dimension

        def _vider_cache_dimensions(**_kwargs):
            cache.delete("scoring:dimensions_actives")
            # Le contenu public dépend aussi des dimensions (cf. views).
            cache.delete_many(["public:dimensions_contenu", "public:accueil_chiffres"])

        post_save.connect(_vider_cache_dimensions, sender=Dimension, weak=False)
        post_delete.connect(_vider_cache_dimensions, sender=Dimension, weak=False)
