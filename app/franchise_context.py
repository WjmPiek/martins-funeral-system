from flask import session
from flask_login import current_user
from app.models import Franchise


def is_privileged_user():
    if not current_user.is_authenticated:
        return False
    return current_user.has_permission("franchise_management:view") or current_user.has_permission("franchise_management:manage")


def get_accessible_franchises():
    if not current_user.is_authenticated:
        return []
    return current_user.accessible_franchises()


def get_selected_franchise():
    franchises = get_accessible_franchises()
    if not franchises:
        return None

    selected_id = session.get("selected_franchise_id")
    if selected_id:
        for franchise in franchises:
            if franchise.id == selected_id:
                return franchise

    selected = franchises[0]
    session["selected_franchise_id"] = selected.id
    return selected


def set_selected_franchise(franchise_id, franchise_view_mode=False):
    if current_user.can_access_franchise(franchise_id):
        session["selected_franchise_id"] = franchise_id
        if franchise_view_mode:
            session["franchise_view_mode"] = True
        return True
    return False


def is_franchise_view_mode():
    if not current_user.is_authenticated:
        return False
    if not is_privileged_user():
        return True
    return bool(session.get("franchise_view_mode"))


def exit_franchise_view_mode():
    session.pop("franchise_view_mode", None)
