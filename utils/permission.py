# access_check.py
from django.urls import reverse

# URL access configuration
URL_ACCESS_MAP = {
    # Public URLs (no restrictions)
    '/login': [],  # Empty list = everyone can access
    
    # User and SuperAdmin URLs
    '/dashboard': ['User', 'SuperAdmin'],
    '/central_news': ['User', 'SuperAdmin'],
    '/files_sharing': ['User', 'SuperAdmin'],
    '/adding_new': ['User', 'SuperAdmin'],
    '/viewAutoNews': ['User', 'SuperAdmin'],
    '/fetch_keyboard': ['User', 'SuperAdmin'],
    '/search_news': ['User', 'SuperAdmin'],
    '/visualize_news': ['User', 'SuperAdmin'],
    '/trending_news': ['User', 'SuperAdmin'],
    '/spy_news': ['User', 'SuperAdmin'],
    '/current_news': ['User', 'SuperAdmin'],
    '/user_track': ['User', 'SuperAdmin'],
    '/source_news': ['User', 'SuperAdmin'],
    '/analyze_comment': ['User', 'SuperAdmin'],
    '/url_catch': ['User', 'SuperAdmin'],
    '/websocket-test': ['User', 'SuperAdmin'],
    '/report_sentiment': ['User', 'SuperAdmin'],
    '/report_news': ['User', 'SuperAdmin'],''
    '/change_password': ['User', 'SuperAdmin'],''
  
    # SuperAdmin only URLs
    '/add_keywords': ['SuperAdmin'],
    '/listing_keyboard': ['SuperAdmin'],
    '/categories/add': ['SuperAdmin'],
    '/categories': ['SuperAdmin'],
    '/users': ['SuperAdmin'],
    'event/': ['SuperAdmin'],
    'threat/<int:pk>/edit/': ['SuperAdmin'],
    'threat/<int:pk>/delete/': ['SuperAdmin'],
    'autonews_list/': ['SuperAdmin'],
    'autonews_edit/<int:pk>/edit/': ['SuperAdmin'],
    'autonews_delete/<int:pk>/delete/': ['SuperAdmin'],    
}

def check_access(request, url_name=None):
    """
    Check if user can access a URL
    Args:
        request: Django request object
        url_name: URL name to check (if None, checks current URL)
    Returns:
        Boolean: True if access allowed, False if denied
    """
    # Get URL path to check
    if url_name:
        try:
            url_path = reverse(url_name)
        except:
            # If URL name not found, assume no access
            return False
    else:
        # Check current request path
        url_path = request.path
    
    # Check if path matches any protected URL
    for url_pattern, allowed_roles in URL_ACCESS_MAP.items():
        if url_path.startswith(url_pattern):
            # If allowed_roles is empty list = public access
            if allowed_roles == []:
                return True
            # Check if user has required role
            user_role = request.session.get('user_role')
            if not user_role:
                return False  # No role = no access to protected pages
            return user_role in allowed_roles
    
    # If URL not in map, allow access (default permissive)
    return True