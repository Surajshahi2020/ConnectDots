from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from collect import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('collect.urls')),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('adding_new/', views.newsfeeding, name='news_feed'),
    path('auto_news/', views.newsAutofeeding, name='news_AutoFeed'),
    path('fetch_keyboard/', views.keyboard_fetch, name='keyboard_fetch'),
    path('autofeed_keyboard/', views.keyboard_AutoFeed, name='keyboard_AutoFeed'),
    path('viewAutoNews/', views.autoNews, name='autonews_view'),
    path('search_news/', views.newsSearching, name='news_search'),
    path('visualize_news/', views.newsVisualization, name='news_visualization'),
    path('trending_news/', views.newsTrending, name='news_trending'),
    path('report_news/', views.newsReport, name='news_report'),
    path('generate_word/', views.generate_word_report, name='generate_word_report'),
    path('current_news/', views.newsCurrent, name='news_current'),
    path('spy_news/', views.newsSpy, name='news_spy'),
    path('login/', views.loginPage, name='login_page'),
    path('', views.loginLogic, name='login_logic'),
    path('log_out/', views.logOut, name='logout'),
    path('signin/', views.signinPage, name='signin_page'),
    path('signin_add/', views.signinAddView, name='signinadd'),
    path('source_news/', views.newsSource, name='news_source'),
    path('analyze_comment/', views.commentAnalyze, name='comment_analyze'),
    path('add_keywords/', views.keywordsAdd, name='keywords_add'), 
    path('listing_keyboard/', views.keyword_listing, name='keywords_listing'),
    path('keywords-edit-<int:id>/', views.keyword_edit, name='keyword_edit'),
    path('keywords-delete-<int:id>/', views.keyword_delete, name='keyword_delete'),
    path('categories/', views.category_list, name='category_list'),
    path('categories-add/', views.category_add, name='category_add'),
    path('categories-edit-<int:category_id>/', views.category_edit, name='category_edit'),
    path('categories-delete-<int:category_id>/', views.category_delete, name='category_delete'),
    path('categories/toggle-status/<int:category_id>/', views.toggle_category_status, name='toggle_category_status'),
    path('categories/bulk-toggle/', views.bulk_toggle_status, name='bulk_toggle_status'),  
    path('map_visualization/', views.visualizationMap, name='visualization_map'),   
    path('create-marker/', views.create_marker, name='create_marker'),
    path('get-markers/', views.get_markers, name='get_markers'), 
    path('delete-marker/', views.delete_marker, name='delete_marker'), 
    path('delete-all-markers/', views.delete_all_markers, name='delete_all_markers'),
    path('update-markers/', views.update_marker, name='update-markers'),
    path('user_manage/', views.manage_user, name='manage_user'),
    path('user_track/', views.track_user, name='track_user'),
    path('social-media/add/', views.add_social_media_url, name='add_social_media_url'),
    path('social-media/list/', views.list_social_media_url, name='list_social_media_url'),\
    path('update/<int:url_id>/', views.update_social_media_url, name='update_social_media_url'),
    path('social_media_dashboard', views.dashboard_social_media, name='dashboard_social_media'),
    path('generate-social-media-report/', views.generate_social_media_report, name='generate_social_media_report'),
    path('social_media_photo', views.photo_social_media, name='photo_social_media'),
    path('url_catch', views.catch_url, name='catch_url'),
    path('report_sentiment', views.sentiment_report, name='sentiment_report'),
    path('check_progress/', views.check_progress, name='check_progress'),
    path('download_exe_file/', views.download_exe_file, name='download_exe_file'),
    path('central_news/', views.news_central, name='news_central'),
    path('like-alert/<int:alert_id>/', views.like_alert, name='like_alert'),
    path('unlike-alert/<int:alert_id>/', views.unlike_alert, name='unlike_alert'),
    # User Management
    path('users/', views.user_list, name='user_list'),
    path('users-add/', views.add_user, name='add_user'),
    path('users-<int:user_id>-edit/', views.edit_user, name='edit_user'),
    path('delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('reset-<int:user_id>/', views.password_reset, name='password_reset'),
    path('change_password/', views.password_change, name='password_change'),
    #Event Management
    path('event/', views.event_list, name='event_list'),
    path('threat-<int:pk>-edit/', views.threat_edit, name='threat_edit'),
    path('threat/<int:pk>/delete/', views.threat_delete, name='threat_delete'),
     #AutoNews Management
    path('autonews_list/', views.list_autonews, name='list_autonews'),
    path('autonews_edit-<int:pk>-edit/', views.edit_autonews, name='edit_autonews'),
    path('autonews_delete/<int:pk>/delete/', views.delete_autonews, name='delete_autonews'),
    #file sharing
    path('files_sharing/', views.sharing_files, name='sharing_files'),
    path('files/delete/<int:file_id>/', views.delete_file, name='delete_file'),
    path('files/download/<int:file_id>/', views.download_shared_file, name='download_shared_file'),
    path('files/share/<int:file_id>/', views.share_file, name='share_file'),
    path('files/bulk-delete/', views.bulk_delete_files, name='bulk_delete_files'),
    #Database Backup
    path('download-database/', views.download_database_backup, name='download_database'),
    #Monitor
    path('sites-monitor', views.monitor_sites, name='monitor_sites'),
    ]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    