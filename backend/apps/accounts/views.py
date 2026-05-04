from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views import View

from .forms import EmailCodeAuthenticationForm, EmailVerificationForm
from .models import EmailLoginCode, User

PENDING_2FA_SESSION_KEY = "pending_2fa_user_id"
PENDING_2FA_NEXT_KEY = "pending_2fa_next"
EMAIL_CODE_EXPIRY_MINUTES = 10
EMAIL_CODE_MAX_ATTEMPTS = 5
EMAIL_CODE_RESEND_SECONDS = 60


def user_requires_email_2fa(user: User) -> bool:
    return bool(user.is_superuser or user.is_staff or user.role == "admin")


def clear_pending_2fa_session(request) -> None:
    request.session.pop(PENDING_2FA_SESSION_KEY, None)
    request.session.pop(PENDING_2FA_NEXT_KEY, None)


def get_pending_2fa_user(request) -> User | None:
    user_id = request.session.get(PENDING_2FA_SESSION_KEY)
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        clear_pending_2fa_session(request)
        return None


def generate_email_login_code(user: User) -> str:
    recent_code = user.email_login_codes.filter(consumed_at__isnull=True).order_by("-created_at").first()
    if recent_code and (timezone.now() - recent_code.created_at).total_seconds() < EMAIL_CODE_RESEND_SECONDS:
        raise ValueError("Er is recent al een verificatiecode verzonden. Probeer het zo opnieuw.")

    user.email_login_codes.filter(consumed_at__isnull=True).update(consumed_at=timezone.now())
    code = f"{secrets.randbelow(1_000_000):06d}"
    EmailLoginCode.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=timezone.now() + timedelta(minutes=EMAIL_CODE_EXPIRY_MINUTES),
    )
    return code


def send_email_login_code(user: User, code: str) -> None:
    context = {
        "user": user,
        "code": code,
        "expiry_minutes": EMAIL_CODE_EXPIRY_MINUTES,
    }
    subject = "Je verificatiecode voor Factuurcontrole"
    text_body = render_to_string("registration/email_login_code.txt", context)
    html_body = render_to_string("registration/email_login_code.html", context)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)


def issue_email_login_code(user: User) -> None:
    if not user.email:
        raise ValueError("Deze gebruiker heeft geen e-mailadres en kan geen e-mailcode ontvangen.")
    code = generate_email_login_code(user)
    send_email_login_code(user, code)


def get_active_email_code(user: User) -> EmailLoginCode | None:
    return user.email_login_codes.filter(consumed_at__isnull=True).order_by("-created_at").first()


class LoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailCodeAuthenticationForm
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            clear_pending_2fa_session(request)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        if not user_requires_email_2fa(user):
            clear_pending_2fa_session(self.request)
            return super().form_valid(form)

        clear_pending_2fa_session(self.request)
        try:
            issue_email_login_code(user)
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        except Exception:
            form.add_error(None, "De verificatiecode kon niet worden verstuurd. Controleer de e-mailinstellingen.")
            return self.form_invalid(form)

        self.request.session[PENDING_2FA_SESSION_KEY] = user.pk
        self.request.session[PENDING_2FA_NEXT_KEY] = self.get_success_url()
        messages.info(self.request, f"Er is een verificatiecode verzonden naar {user.email}.")
        return redirect("login_verify")


class EmailVerificationView(View):
    template_name = "registration/verify_login.html"
    form_class = EmailVerificationForm

    def get(self, request, *args, **kwargs):
        user = get_pending_2fa_user(request)
        if not user:
            return redirect("login")
        form = self.form_class()
        return render(request, self.template_name, {"form": form, "pending_user": user})

    def post(self, request, *args, **kwargs):
        user = get_pending_2fa_user(request)
        if not user:
            return redirect("login")

        if "resend" in request.POST:
            try:
                issue_email_login_code(user)
                messages.success(request, f"Er is een nieuwe verificatiecode verzonden naar {user.email}.")
            except ValueError as exc:
                messages.error(request, str(exc))
            except Exception:
                messages.error(request, "De verificatiecode kon niet opnieuw worden verstuurd.")
            return redirect("login_verify")

        form = self.form_class(request.POST)
        active_code = get_active_email_code(user)
        if not active_code:
            form.add_error(None, "Er is geen actieve verificatiecode meer. Vraag een nieuwe code aan.")
            return render(request, self.template_name, {"form": form, "pending_user": user})

        if active_code.is_consumed or active_code.is_expired:
            active_code.consumed_at = timezone.now()
            active_code.save(update_fields=["consumed_at", "updated_at"])
            form.add_error(None, "De verificatiecode is verlopen. Vraag een nieuwe code aan.")
            return render(request, self.template_name, {"form": form, "pending_user": user})

        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "pending_user": user})

        active_code.attempts += 1
        if active_code.attempts >= EMAIL_CODE_MAX_ATTEMPTS and not check_password(form.cleaned_data["code"], active_code.code_hash):
            active_code.consumed_at = timezone.now()
        active_code.save(update_fields=["attempts", "consumed_at", "updated_at"] if active_code.consumed_at else ["attempts", "updated_at"])

        if not check_password(form.cleaned_data["code"], active_code.code_hash):
            remaining = max(0, EMAIL_CODE_MAX_ATTEMPTS - active_code.attempts)
            if remaining == 0:
                form.add_error(None, "Te veel onjuiste pogingen. Vraag een nieuwe code aan.")
            else:
                form.add_error(None, f"Onjuiste verificatiecode. Nog {remaining} poging(en).")
            return render(request, self.template_name, {"form": form, "pending_user": user})

        active_code.consumed_at = timezone.now()
        active_code.save(update_fields=["consumed_at", "updated_at"])
        next_url = request.session.get(PENDING_2FA_NEXT_KEY) or settings.LOGIN_REDIRECT_URL
        clear_pending_2fa_session(request)
        user.backend = "django.contrib.auth.backends.ModelBackend"
        auth_login(request, user)
        return redirect(next_url)


class LogoutView(auth_views.LogoutView):
    def dispatch(self, request, *args, **kwargs):
        clear_pending_2fa_session(request)
        return super().dispatch(request, *args, **kwargs)
