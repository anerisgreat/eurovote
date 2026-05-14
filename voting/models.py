from django.db import models
from django.contrib.auth.models import User


class Vote(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='votes')
    entry_id   = models.CharField(max_length=50)   # e.g. "2026_norway"
    event_year = models.PositiveSmallIntegerField()  # e.g. 2026
    nickname               = models.CharField(max_length=200)
    performance_rating     = models.PositiveSmallIntegerField(null=True, blank=True)
    visuals_rating         = models.PositiveSmallIntegerField(null=True, blank=True)
    singing_rating         = models.PositiveSmallIntegerField(null=True, blank=True)
    song_production_rating = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        unique_together = [('user', 'entry_id')]

    def __str__(self):
        return f"{self.user.username} → {self.entry_id}: {self.nickname}"

    @property
    def entry(self):
        from .entry_registry import get_entry
        return get_entry(self.entry_id)


class RankingEntry(models.Model):
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ranking_entries')
    vote     = models.ForeignKey(Vote, on_delete=models.CASCADE, related_name='ranking_entries')
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"{self.user.username} #{self.position}: {self.vote.entry_id}"
