# middleware.py
from django.shortcuts import redirect

class RoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        current_path = request.path
        
        # ========== PUBLIC ACCESS ==========
        # Allow Django admin, static files, and public pages
        if current_path.startswith('/admin/'):
            return self.get_response(request)
        
        if current_path.startswith('/static/') or current_path.startswith('/media/'):
            return self.get_response(request)
        
        public_pages = [
            '/', 
            '/login/', 
            '/signin/', 
            '/log_out/', 
            '/signin_add/',
            '/accounts/login/',
            '/accounts/logout/',
        ]
        
        if current_path in public_pages:
            return self.get_response(request)
        
        # ========== AUTHENTICATION CHECK ==========
        user_role = request.session.get('user_role', 'User')
        is_authenticated = request.session.get('auth', False)
        
        if not is_authenticated:
            request.session['next_url'] = current_path
            request.session['error_message'] = 'Please login first.'
            return redirect('login_page')
        
        # ========== ROLE-BASED ACCESS CONTROL ==========
        
        # Define role permissions
        role_permissions = {
            'SuperAdmin': {
                'allowed_patterns': ['*'],  # Access to everything
                'redirect_on_deny': None
            },
            'Admin': {
                'allowed_patterns': ['*'],  # Access to everything except what's explicitly denied
                'denied_patterns': [
                    '/signin_add/',  # Only SuperAdmin can add users
                ],
                'redirect_on_deny': 'dashboard'
            },
            'User': {
                'allowed_patterns': [
                    '/dashboard/',
                    '/profile/',
                    '/social-media/',
                ],
                'denied_patterns': [
                    '/auto_news/',
                    '/add_keywords/',
                    '/create-marker/',
                    '/delete-marker/',
                    '/delete-all-markers/',
                    '/update-markers/',
                ],
                'redirect_on_deny': 'dashboard'
            },
            'CyberUser': {
                'allowed_patterns': [
                    # Social Media Dashboard
                    '/social_media_dashboard',
                    '/social_media_dashboard/',
                    
                    # Social Media URLs Management
                    '/social-media/add/',
                    '/social-media/add',  # Without trailing slash
                    '/social-media/list/',
                    '/social-media/list',
                    '/social_media_photo',
                    
                    # Update URLs
                    '/update/',  # Pattern for all update URLs
                    
                    # Report Generation
                    '/generate-social-media-report/',
                    '/generate-social-media-report',  # Without trailing slash
                    
                    # Any social-media related paths
                    '/social-media/',
                ],
                'redirect_on_deny': 'dashboard_social_media'
            }
        }
        
        # Get permissions for current role
        permissions = role_permissions.get(user_role, role_permissions['User'])
        
        # ========== SUPER ADMIN ==========
        if user_role == 'SuperAdmin':
            return self.get_response(request)
        
        # ========== ADMIN ==========
        elif user_role == 'Admin':
            if 'denied_patterns' in permissions:
                for pattern in permissions['denied_patterns']:
                    if current_path.startswith(pattern):
                        request.session['error_message'] = 'Only SuperAdmin can access this.'
                        return redirect(permissions['redirect_on_deny'])
            return self.get_response(request)
        
        # ========== USER ==========
        elif user_role == 'User':
            if 'denied_patterns' in permissions:
                for pattern in permissions['denied_patterns']:
                    if current_path.startswith(pattern):
                        request.session['error_message'] = 'Access denied! Admin privileges required.'
                        return redirect(permissions['redirect_on_deny'])
            return self.get_response(request)
        
        # ========== CYBER USER ==========
        elif user_role == 'CyberUser':
            access_granted = False
            
            # Check allowed patterns
            for pattern in permissions['allowed_patterns']:
                # Check exact match
                if current_path == pattern:
                    access_granted = True
                    break
                
                # Check if current path starts with pattern (for patterns ending with /)
                if pattern.endswith('/') and current_path.startswith(pattern):
                    access_granted = True
                    break
                
                # Check if current path starts with pattern + / (for patterns without trailing slash)
                if not pattern.endswith('/') and (current_path == pattern or current_path.startswith(pattern + '/')):
                    access_granted = True
                    break
            
            # Special handling for /update/<int:url_id>/ pattern
            if not access_granted and current_path.startswith('/update/'):
                # Check if it's a valid update URL (contains digits for url_id)
                import re
                update_pattern = r'^/update/\d+/$'  # Pattern for /update/123/
                if re.match(update_pattern, current_path):
                    access_granted = True
            
            if access_granted:
                return self.get_response(request)
            else:
                # Redirect CyberUser to social media dashboard
                request.session['error_message'] = 'CyberUser can only access Social Media features.'
                return redirect('dashboard_social_media')
        
        # ========== DEFAULT REDIRECT ==========
        else:
            request.session['error_message'] = 'Invalid user role. Please login again.'
            return redirect('login_page')