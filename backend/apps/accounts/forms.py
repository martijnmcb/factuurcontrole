from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm


class EmailCodeAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Gebruikersnaam", widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Wachtwoord", strip=False, widget=forms.PasswordInput)


class EmailVerificationForm(forms.Form):
    code = forms.CharField(
        label="Verificatiecode",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )

    def clean_code(self):
        code = "".join(ch for ch in self.cleaned_data["code"] if ch.isdigit())
        if len(code) != 6:
            raise forms.ValidationError("Voer een geldige 6-cijferige code in.")
        return code
