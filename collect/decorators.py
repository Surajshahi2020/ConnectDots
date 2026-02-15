# your_app/decorators.py
from django.shortcuts import redirect

def session_auth_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.session.get("auth") == True:
            return view_func(request, *args, **kwargs)
        return redirect("/login")
    return wrapper
