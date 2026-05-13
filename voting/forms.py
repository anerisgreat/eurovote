from django import forms


class VoteForm(forms.Form):
    nickname = forms.CharField(
        max_length=200,
        label="Quick note to remember this performance",
        widget=forms.TextInput(attrs={'autofocus': True, 'placeholder': 'e.g. "the one with the giant hamster wheel"'}),
    )
