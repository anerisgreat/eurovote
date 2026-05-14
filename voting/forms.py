from django import forms


def _rating_field(label):
    return forms.IntegerField(
        label=label,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={'min': '1', 'max': '10', 'class': 'rating-input'}),
    )


class VoteForm(forms.Form):
    nickname = forms.CharField(
        max_length=200,
        label="Quick note to remember this performance",
        widget=forms.TextInput(attrs={'autofocus': True, 'placeholder': 'e.g. "the one with the giant hamster wheel"'}),
    )
    performance_rating     = _rating_field("Performance")
    visuals_rating         = _rating_field("Visuals")
    singing_rating         = _rating_field("Singing")
    song_production_rating = _rating_field("Song & Production")
