import io
import math
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
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
def ranking_image(request, year):
    from PIL import Image, ImageDraw, ImageFont

    event = _get_event_or_404(year)
    ranking = list(
        RankingEntry.objects
        .filter(user=request.user, vote__event_year=year)
        .order_by('position')
        .select_related('vote')
    )
    if not ranking:
        raise Http404("No ranking to export")

    # ── Palette ──────────────────────────────────────────────────────────────
    C_BG     = (13,  13,  26)
    C_BG_ALT = (18,  18,  42)
    C_HDR    = (20,  20,  50)
    C_PURPLE = (108, 99,  255)
    C_WHITE  = (255, 255, 255)
    C_GRAY   = (192, 192, 224)
    C_DIM    = (128, 128, 160)
    C_NOTE   = (160, 160, 255)
    C_LINE   = (42,  42,  80)

    # ── Fonts ────────────────────────────────────────────────────────────────
    try:
        f_body = ImageFont.load_default(size=14)
        f_sm   = ImageFont.load_default(size=12)
        f_lg   = ImageFont.load_default(size=22)
    except TypeError:
        f_body = f_sm = f_lg = ImageFont.load_default()

    # ── Layout ───────────────────────────────────────────────────────────────
    PAD    = 36
    ROW_H  = 34
    HDR_H  = 86
    THDR_H = 28

    # (label, width, align)
    COLS = [
        ('#',         36,  'right'),
        ('Country',   162, 'left'),
        ('Artist',    150, 'left'),
        ('Song',      150, 'left'),
        ('Note',      140, 'left'),
        ('Perf',       44, 'center'),
        ('Visuals',    44, 'center'),
        ('Singing',    44, 'center'),
        ('Song/Prod',  56, 'center'),
    ]
    GAP = 10

    content_w = sum(c[1] for c in COLS) + GAP * (len(COLS) - 1)
    width  = content_w + PAD * 2
    height = HDR_H + THDR_H + ROW_H * len(ranking) + PAD

    img  = Image.new('RGB', (width, height), C_BG)
    draw = ImageDraw.Draw(img)

    def col_x(i):
        return PAD + sum(COLS[j][1] + GAP for j in range(i))

    def fit(text, max_w, font):
        if not text:
            return ''
        try:
            if draw.textlength(text, font=font) <= max_w:
                return text
            while text and draw.textlength(text + '…', font=font) > max_w:
                text = text[:-1]
            return text + '…' if text else ''
        except Exception:
            return text[:int(max_w / 8)]  # rough fallback

    def draw_cell(col_i, y, text, font, color, v_off=0):
        label, w, align = COLS[col_i]
        x  = col_x(col_i)
        t  = fit(str(text), w, font)
        try:
            tw = draw.textlength(t, font=font)
        except Exception:
            tw = len(t) * 8
        if align == 'right':
            draw.text((x + w - tw, y + v_off), t, fill=color, font=font)
        elif align == 'center':
            draw.text((x + (w - tw) / 2, y + v_off), t, fill=color, font=font)
        else:
            draw.text((x, y + v_off), t, fill=color, font=font)

    # ── Header ───────────────────────────────────────────────────────────────
    draw.rectangle([(0, 0), (width, HDR_H)], fill=C_HDR)
    draw.text((PAD, 20), event.name, fill=C_WHITE, font=f_lg)
    draw.text((PAD, 52), f"{request.user.username}'s personal ranking", fill=C_DIM, font=f_body)
    draw.rectangle([(0, HDR_H - 3), (width, HDR_H)], fill=C_PURPLE)

    # ── Column headers ───────────────────────────────────────────────────────
    ty = HDR_H
    draw.rectangle([(0, ty), (width, ty + THDR_H)], fill=C_HDR)
    for i, (label, w, align) in enumerate(COLS):
        draw_cell(i, ty + 7, label, f_sm, C_DIM)
    draw.line([(0, ty + THDR_H - 1), (width, ty + THDR_H - 1)], fill=C_LINE)

    # ── Rows ─────────────────────────────────────────────────────────────────
    v_off = (ROW_H - 14) // 2
    for idx, r in enumerate(ranking):
        y = HDR_H + THDR_H + idx * ROW_H
        draw.rectangle([(0, y), (width, y + ROW_H)], fill=C_BG_ALT if idx % 2 == 0 else C_BG)

        vote  = r.vote
        entry = vote.entry
        draw_cell(0, y, idx + 1,                                          f_body, C_PURPLE, v_off)
        draw_cell(1, y, entry.country,                                    f_body, C_WHITE,  v_off)
        draw_cell(2, y, entry.artist or '',                               f_body, C_GRAY,   v_off)
        draw_cell(3, y, entry.song_title or '',                           f_body, C_DIM,    v_off)
        draw_cell(4, y, vote.nickname or '',                              f_body, C_NOTE,   v_off)
        draw_cell(5, y, vote.performance_rating     or '—',               f_body, C_GRAY,   v_off)
        draw_cell(6, y, vote.visuals_rating         or '—',               f_body, C_GRAY,   v_off)
        draw_cell(7, y, vote.singing_rating         or '—',               f_body, C_GRAY,   v_off)
        draw_cell(8, y, vote.song_production_rating or '—',               f_body, C_GRAY,   v_off)

        draw.line([(PAD, y + ROW_H - 1), (width - PAD, y + ROW_H - 1)], fill=C_LINE)

    # ── Serve ────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    img.save(buf, format='PNG', optimize=True)
    buf.seek(0)

    filename = f"eurovision_{year}_{request.user.username}_ranking.png"
    response = HttpResponse(buf, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


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
