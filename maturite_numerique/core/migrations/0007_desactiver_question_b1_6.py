from django.db import migrations


def desactiver_b1_6(apps, schema_editor):
    """Le mode de saisie est déterminé par le contexte (enquêteur assisté /
    lien public autonome), plus par une question. On désactive B1.6 s'il
    existe déjà en base ; les nouvelles installations ne la créent plus."""
    Question = apps.get_model("core", "Question")
    Question.objects.filter(
        code="B1.6", version_formulaire__formulaire__code="B"
    ).update(actif=False)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_administration_enqueteurs"),
    ]

    operations = [
        migrations.RunPython(desactiver_b1_6, migrations.RunPython.noop),
    ]
