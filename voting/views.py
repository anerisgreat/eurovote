import math
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.db.models import F

from .models import Vote, RankingEntry
from .forms import VoteForm
from .entry_registry import get_entry, get_event, get_all_events


def _get_event_or_404(year):
    event = get_event(year)
    if event is None:
        raise Http404(f"No event data for year {year}")
    return event


def _get_ranked_vote_ids(user, year):
    return list(
        RankingEntry.objects
        .filter(user=user, vote__event_year=year)
        .order_by('position')
        .values_list('vote_id', flat=True)
    )


def _next_unvoted_entry(user, event):
    voted_ids = set(
        Vote.objects.filter(user=user, event_year=event.year)
        .values_list('entry_id', flat=True)
    )
    for entry in event.entries:
        if entry.entry_id not in voted_ids:
            return entry
    return None


def event_list(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'voting/event_list.html', {'events': get_all_events()})


SORT_KEYS = {
    'ranking':              lambda r: r.position,
    'show_order':           lambda r: r.vote.entry.performance_order,
    'performance_rating':   lambda r: -(r.vote.performance_rating or 0),
    'visuals_rating':       lambda r: -(r.vote.visuals_rating or 0),
    'singing_rating':       lambda r: -(r.vote.singing_rating or 0),
    'song_production_rating': lambda r: -(r.vote.song_production_rating or 0),
}


@login_required
def index(request, year):
    event = _get_event_or_404(year)
    sort = request.GET.get('sort', 'ranking')
    if sort not in SORT_KEYS:
        sort = 'ranking'

    ranking = list(
        RankingEntry.objects
        .filter(user=request.user, vote__event_year=year)
        .order_by('position')
        .select_related('vote')
    )
    ranking.sort(key=SORT_KEYS[sort])

    total_entries = len(event.entries)
    voted_count = Vote.objects.filter(user=request.user, event_year=year).count()
    next_entry = _next_unvoted_entry(request.user, event)

    orphaned_votes = Vote.objects.filter(
        user=request.user,
        event_year=year,
        ranking_entries__isnull=True,
    )

    return render(request, 'voting/index.html', {
        'event': event,
        'ranking': ranking,
        'sort': sort,
        'total_entries': total_entries,
        'voted_count': voted_count,
        'next_entry': next_entry,
        'orphaned_votes': orphaned_votes,
    })


@login_required
def vote_next(request, year):
    event = _get_event_or_404(year)
    entry = _next_unvoted_entry(request.user, event)

    if entry is None:
        return redirect('index', year=year)

    if request.method == 'POST':
        form = VoteForm(request.POST)
        if form.is_valid():
            vote = Vote.objects.create(
                user=request.user,
                entry_id=entry.entry_id,
                event_year=year,
                nickname=form.cleaned_data['nickname'],
                performance_rating=form.cleaned_data['performance_rating'],
                visuals_rating=form.cleaned_data['visuals_rating'],
                singing_rating=form.cleaned_data['singing_rating'],
                song_production_rating=form.cleaned_data['song_production_rating'],
            )

            ranked_ids = _get_ranked_vote_ids(request.user, year)

            if not ranked_ids:
                RankingEntry.objects.create(user=request.user, vote=vote, position=0)
                return redirect('index', year=year)

            request.session['bsort'] = {
                'year': year,
                'new_vote_id': vote.pk,
                'ranked_ids': ranked_ids,
                'left': 0,
                'right': len(ranked_ids),
            }
            return redirect('compare', year=year)
    else:
        form = VoteForm()

    return render(request, 'voting/vote_next.html', {
        'event': event,
        'entry': entry,
        'form': form,
    })


@login_required
def rerank(request, year, vote_id):
    _get_event_or_404(year)
    vote = get_object_or_404(Vote, pk=vote_id, user=request.user, event_year=year)
    ranking_entry = RankingEntry.objects.filter(vote=vote, user=request.user).first()

    if ranking_entry:
        pos = ranking_entry.position
        ranking_entry.delete()
        RankingEntry.objects.filter(
            user=request.user,
            vote__event_year=year,
            position__gt=pos,
        ).update(position=F('position') - 1)

    ranked_ids = _get_ranked_vote_ids(request.user, year)

    if not ranked_ids:
        RankingEntry.objects.create(user=request.user, vote=vote, position=0)
        return redirect('index', year=year)

    request.session['bsort'] = {
        'year': year,
        'new_vote_id': vote.pk,
        'ranked_ids': ranked_ids,
        'left': 0,
        'right': len(ranked_ids),
    }
    return redirect('compare', year=year)


@login_required
def compare(request, year):
    event = _get_event_or_404(year)
    state = request.session.get('bsort')

    if not state or state.get('year') != year:
        return redirect('index', year=year)

    left = state['left']
    right = state['right']
    ranked_ids = state['ranked_ids']
    new_vote_id = state['new_vote_id']

    new_vote = get_object_or_404(Vote, pk=new_vote_id, user=request.user)
    comp_index = (left + right) // 2
    comp_vote = get_object_or_404(Vote, pk=ranked_ids[comp_index], user=request.user)

    if request.method == 'POST':
        choice = request.POST.get('choice')
        if choice == '1':
            left = comp_index + 1
        elif choice == '2':
            right = comp_index
        else:
            return redirect('compare', year=year)

        if left == right:
            ins_pos = left
            RankingEntry.objects.filter(
                user=request.user,
                vote__event_year=year,
                position__gte=ins_pos,
            ).update(position=F('position') + 1)
            RankingEntry.objects.create(user=request.user, vote=new_vote, position=ins_pos)
            del request.session['bsort']
            return redirect('index', year=year)

        state['left'] = left
        state['right'] = right
        request.session.modified = True
        return redirect('compare', year=year)

    remaining = math.ceil(math.log2(right - left + 1)) if right > left else 0

    return render(request, 'voting/compare.html', {
        'event': event,
        'new_vote': new_vote,
        'comp_vote': comp_vote,
        'remaining': remaining,
    })
