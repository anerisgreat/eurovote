from django.contrib import admin
from .models import Vote, RankingEntry


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ['user', 'entry_id', 'event_year', 'nickname']
    list_filter = ['event_year']


@admin.register(RankingEntry)
class RankingEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'position', 'vote']
    list_filter = ['vote__event_year']
    ordering = ['user', 'position']
