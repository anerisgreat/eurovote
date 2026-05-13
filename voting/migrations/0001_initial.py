from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Vote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('entry_id', models.CharField(max_length=50)),
                ('event_year', models.PositiveSmallIntegerField()),
                ('nickname', models.CharField(max_length=200)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='votes', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='vote',
            constraint=models.UniqueConstraint(fields=('user', 'entry_id'), name='unique_user_entry_vote'),
        ),
        migrations.CreateModel(
            name='RankingEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveSmallIntegerField()),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ranking_entries', to=settings.AUTH_USER_MODEL)),
                ('vote', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ranking_entries', to='voting.vote')),
            ],
            options={
                'ordering': ['position'],
            },
        ),
    ]
